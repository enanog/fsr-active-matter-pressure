function dG = delta_g(P, deltaT_s)
% DELTA_G  dG(t) = G(t) - G(t - deltaT) on the sensor grid [uS]; NaN where either end falls outside
% the FSRScope mask, so excluded or cropped sections never leak into the differences.
    L = max(1, round(deltaT_s / P.paso));
    n = numel(P.G);
    dG = nan(n, 1);
    if L >= n, return; end
    dG(L + 1:end) = P.G(L + 1:end) - P.G(1:end - L);
    ok = false(n, 1);
    ok(L + 1:end) = P.mascara(L + 1:end) & P.mascara(1:end - L);
    dG(~ok) = NaN;
end
