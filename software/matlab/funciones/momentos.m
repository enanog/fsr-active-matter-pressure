function [asim, curt] = momentos(x)
% MOMENTOS  Bias-corrected sample skewness and excess kurtosis (same as FSRScope, pandas .skew()/.kurt()
% and Excel SKEW()/KURT()). NaN values are ignored.
    x = x(isfinite(x));
    n = numel(x);
    asim = NaN;  curt = NaN;
    if n < 4, return; end
    c = x - mean(x);
    m2 = mean(c .^ 2);
    if m2 <= 0, return; end
    g1 = mean(c .^ 3) / m2 ^ 1.5;
    g2 = mean(c .^ 4) / m2 ^ 2 - 3;
    asim = sqrt(n * (n - 1)) / (n - 2) * g1;
    curt = ((n + 1) * g2 + 6) * (n - 1) / ((n - 2) * (n - 3));
end
