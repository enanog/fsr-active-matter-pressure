function [deltaT, asim, curt] = momentos_vs_deltaT(P, deltaT_max, paso_deltaT)
% MOMENTOS_VS_DELTAT  Skewness and kurtosis of dG = G(t) - G(t - deltaT) for deltaT = paso..deltaT_max
% (default: the FSRScope sweep, every grid step up to P.deltaT_max), over the masked samples.
    if nargin < 2 || isempty(deltaT_max), deltaT_max = P.deltaT_max; end
    if nargin < 3 || isempty(paso_deltaT), paso_deltaT = P.paso; end
    lags = unique(max(1, round((paso_deltaT:paso_deltaT:deltaT_max) / P.paso)));
    deltaT = lags(:) * P.paso;
    asim = nan(numel(lags), 1);  curt = asim;
    n = numel(P.G);
    for i = 1:numel(lags)
        L = lags(i);
        if L >= n, break; end
        ok = P.mascara(L + 1:end) & P.mascara(1:end - L);
        d = P.G(L + 1:end) - P.G(1:end - L);
        [asim(i), curt(i)] = momentos(d(ok));
    end
end
