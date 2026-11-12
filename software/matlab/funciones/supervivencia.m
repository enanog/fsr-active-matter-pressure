function [x, p] = supervivencia(v)
% SUPERVIVENCIA  Empirical survival function P(X >= x): x sorted ascending, p from 1 down to 1/n.
    x = sort(v(isfinite(v)));
    x = x(:);
    n = numel(x);
    p = (n:-1:1)' / n;
end
