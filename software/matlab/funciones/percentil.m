function p = percentil(A, q, dim)
% PERCENTIL  q-th percentile (0-100) ignoring NaN, linear interpolation (same as numpy.nanpercentile).
% No Statistics Toolbox needed. dim = 1 (columns, default for matrices) or 2 (each row); vectors: all.
    if nargin < 3
        if isvector(A), A = A(:); end
        dim = 1;
    end
    if dim == 2, A = A.'; end
    A = sort(A, 1);                                 % NaN go to the end
    n = sum(isfinite(A), 1);
    pos = q / 100 * (n - 1) + 1;
    lo = floor(pos);  hi = ceil(pos);
    c = 1:size(A, 2);
    lo(n == 0) = 1;  hi(n == 0) = 1;
    a = A(sub2ind(size(A), lo, c));
    b = A(sub2ind(size(A), hi, c));
    p = a + (pos - lo) .* (b - a);
    p(n == 0) = NaN;
    if dim == 2, p = p.'; end
end
