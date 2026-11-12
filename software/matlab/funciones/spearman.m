function rho = spearman(x, y)
% SPEARMAN  Spearman rank correlation (no Statistics Toolbox needed; ties are negligible here).
    ok = isfinite(x) & isfinite(y);
    n = nnz(ok);
    if n < 10, rho = NaN; return; end
    rx = zeros(n, 1);  ry = rx;
    [~, ix] = sort(x(ok));  rx(ix) = 1:n;
    [~, iy] = sort(y(ok));  ry(iy) = 1:n;
    r = corrcoef(rx, ry);
    rho = r(1, 2);
end
