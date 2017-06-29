# -*- coding: utf-8 -*-


import pandas as pd
import numpy as np
import copy
from sklearn.base import (BaseEstimator,
                          TransformerMixin)
from sklearn_pandas import DataFrameMapper
from PyFin.Utilities import pyFinAssert
from argcheck import preprocess
from itertools import chain
from .preprocess import (ensure_factor_container,
                         FactorTransformer)
from .enums import (FactorType,
                    SelectionMethod)
from .const import (INDEX_SELECTOR,
                    INDEX_FACTOR,
                    INDEX_INDUSTRY_WEIGHT)
from .utils import ensure_pd_series


class IndustryNeutralSelector(BaseEstimator, TransformerMixin):
    @preprocess(industry_weight=ensure_pd_series)
    def __init__(self, industry_weight, prop_select=0.1, min_select_per_industry=2, out_full=False, reset_index=False):
        self.industry_weight = industry_weight
        self.prop_select = prop_select
        self.min_select_per_industry = min_select_per_industry
        self.score = None
        self.industry_code = None
        self.out_full = out_full
        self.reset_index = reset_index

    def fit(self, X, **kwargs):
        try:
            col_score = kwargs.get('col_score', 'score')
            col_industry_code = kwargs.get('col_score', 'industry_code')
            self.score = X[col_score]
            self.industry_code = X[col_industry_code]
        except KeyError:
            raise KeyError('Fail to retrieve data: please either use default col names or reset them')
        return self

    def transform(self, X):
        """
        :param X: pd.DataFrame
        :return: 
        """

        ret = pd.DataFrame()
        for name, group in X.groupby(self.industry_code.name):
            try:
                weight = self.industry_weight[name]
            except KeyError:
                continue
            if weight == 0:
                continue

            nb_select = int(max(len(group) * self.prop_select, min(self.min_select_per_industry, len(group))))
            largest_score = group.nlargest(n=nb_select, columns=self.score.name)
            weight_append = pd.DataFrame({INDEX_SELECTOR.col_name: [weight / nb_select] * nb_select,
                                          self.industry_code.name: [name] * nb_select},
                                         index=largest_score.index)

            ret = pd.concat([ret, pd.concat([largest_score[self.score.name], weight_append], axis=1)],
                            axis=0) if self.out_full else pd.concat([ret, weight_append], axis=0)

        return ret.reset_index() if self.reset_index else ret


class BrutalSelector(BaseEstimator, TransformerMixin):
    def __init__(self, nb_select=10, prop_select=0.1, out_full=False, reset_index=False):
        self.nb_select = nb_select
        self.prop_select = prop_select
        self.out_full = out_full
        self.reset_index = reset_index

    def fit(self, X):
        return self

    @preprocess(X=ensure_pd_series)
    def transform(self, X):
        """
        :param X: pd.Series
        :return: 
        """

        ret = pd.DataFrame()
        nb_select = self.nb_select if self.nb_select is not None else int(len(X) * self.prop_select)
        largest_score = X.nlargest(n=nb_select)
        weight = [100.0 / nb_select] * nb_select
        weight_append = pd.DataFrame({INDEX_SELECTOR.col_name: weight}, index=largest_score.index)
        if self.out_full:
            weight_append = pd.concat([largest_score, weight_append], axis=1)
        ret = pd.concat([ret, weight_append], axis=0)

        return ret.reset_index() if self.reset_index else ret


class Selector(FactorTransformer):
    def __init__(self,
                 industry_weight=None,
                 method=SelectionMethod.INDUSTRY_NEUTRAL,
                 nb_select=10,
                 prop_select=0.1,
                 copy=True,
                 groupby_date=True,
                 out_container=False,
                 **kwargs):
        super(Selector, self).__init__(copy=copy, groupby_date=groupby_date, out_container=out_container)
        self.method = method
        self.nb_select = nb_select
        self.prop_select = prop_select
        self.industry_weight = industry_weight
        self.min_select_per_industry = kwargs.get('min_select_per_industry', 2)
        self.out_full = kwargs.get('out_full', False)

    def _build_mapper(self, factor_container):
        data_mapper_by_date = pd.Series()
        industry_code = factor_container.industry_code
        score = factor_container.score
        for date in factor_container.tiaocang_date:
            if self.method == SelectionMethod.INDUSTRY_NEUTRAL:
                pyFinAssert(self.industry_weight is not None, ValueError, 'industry weight has not been given')
                industry_weight = self.industry_weight.loc[date]
                data_mapper = [([score.name, industry_code.name],
                                IndustryNeutralSelector(industry_weight=industry_weight,
                                                        prop_select=self.prop_select,
                                                        min_select_per_industry=self.min_select_per_industry,
                                                        out_full=self.out_full,
                                                        reset_index=True))]
            else:
                data_mapper = [(score.name, BrutalSelector(nb_select=self.nb_select,
                                                           prop_select=self.prop_select,
                                                           out_full=self.out_full,
                                                           reset_index=True))]
            data_mapper_by_date[date] = DataFrameMapper(data_mapper, input_df=True)

        return data_mapper_by_date

    @preprocess(factor_container=ensure_factor_container)
    def transform(self, factor_container, **kwargs):
        if self.copy:
            factor_container = copy.deepcopy(factor_container)
        if not self.groupby_date:
            selector_data_agg = self.df_mapper.fit_transform(factor_container.data)
        else:
            tiaocang_date = factor_container.tiaocang_date
            selector_data = [self.df_mapper[date_].fit_transform(factor_container.data.loc[date_]) for date_ in
                             tiaocang_date]
            date_list = [[tiaocang_date[i]]*len(selector_data[i]) for i in range(len(selector_data))]
            date_agg = list(chain.from_iterable(date_list))
            selector_data_agg = np.hstack(selector_data)

        data_df = pd.DataFrame(selector_data_agg)
        data_df.set_index(data_df.columns[0], data_df.columns[1])
        factor_container.data = data_df
        if self.out_container:
            return factor_container
        else:
            return factor_container.data
