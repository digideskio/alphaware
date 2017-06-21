from PyFin.Utilities import (pyFinWarning,
                             pyFinAssert)
from sklearn.pipeline import (_name_estimators,
                              Pipeline)
from sklearn.utils import tosequence
import six
import copy
from ..preprocess import FactorContainer


def _call_fit(fit_method, X, y=None, **kwargs):
    """
    helper function, calls the fit or fit_transform method with the correct
    number of parameters

    https://github.com/pandas-dev/sklearn-pandas/blob/master/sklearn_pandas/pipeline.py
    """
    try:
        return fit_method(X, y, **kwargs)
    except TypeError:
        # fit takes only one argument
        return fit_method(X, **kwargs)


class AlphaPipeline(Pipeline):
    """
    https://github.com/pandas-dev/sklearn-pandas/blob/master/sklearn_pandas/pipeline.py
    """

    def __init__(self, steps, **kwargs):
        super(AlphaPipeline, self).__init__(steps)
        self._benchmark = kwargs.get('benchmark', None)

        names, estimators = zip(*steps)
        if len(dict(steps)) != len(steps):
            raise ValueError(
                "Provided step names are not unique: %s" % (names,))

        # shallow copy of steps
        self.steps = tosequence(steps)
        estimator = estimators[-1]

        for e in estimators:
            if (not (hasattr(e, "fit") or hasattr(e, "fit_transform")) or not
            hasattr(e, "transform")):
                raise TypeError("All steps of the chain should "
                                "be transforms and implement fit and transform"
                                " '%s' (type %s) doesn't)" % (e, type(e)))

        if not hasattr(estimator, "fit"):
            raise TypeError("Last step of chain should implement fit "
                            "'%s' (type %s) doesn't)"
                            % (estimator, type(estimator)))

    def _pre_transform(self, factor_container, y=None, **fit_params):
        fit_params_steps = dict((step, {}) for step, _ in self.steps)
        for pname, pval in six.iteritems(fit_params):
            step, param = pname.split('__', 1)
            fit_params_steps[step][param] = pval
        fc = factor_container
        for name, transform in self.steps[:-1]:
            if hasattr(transform, "fit_transform"):
                fc_fit = _call_fit(transform.fit_transform,
                                   fc, y, **fit_params_steps[name])
            else:
                fc_fit = _call_fit(transform.fit,
                                   fc, y, **fit_params_steps[name]).transform(fc)
            fc.replace_data(fc_fit)

        return fc, fit_params_steps[self.steps[-1][0]]

    def fit(self, factor_container, y=None, **fit_params):
        fc_fit, fit_params = self._pre_transform(factor_container, y, **fit_params)
        factor_container.replace_data(fc_fit)
        _call_fit(self.steps[-1][-1].fit, factor_container, y, **fit_params)
        return self

    def fit_transform(self, factor_container, y=None, **fit_params):
        fc_fit, fit_params = self._pre_transform(factor_container, y, **fit_params)
        factor_container.replace_data(fc_fit)
        if hasattr(self.steps[-1][-1], "fit_transform"):
            return _call_fit(self.steps[-1][-1].fit_transform,
                             factor_container, y, **fit_params)
        else:
            return _call_fit(self.steps[-1][-1].fit,
                             factor_container, y, **fit_params).transform(factor_container)
