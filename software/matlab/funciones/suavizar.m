function ys = suavizar(t, y, ventana_s)
% SUAVIZAR  Centred moving average of VENTANA_S seconds (0 = raw) ignoring NaN.
    if nargin < 3 || ventana_s <= 0, ys = y; return; end
    dt = median(diff(t(isfinite(t))));
    k = max(1, round(ventana_s / dt));
    ok = isfinite(y);
    y0 = y;  y0(~ok) = 0;
    w = ones(k, 1);
    ys = conv(y0(:), w, 'same') ./ conv(double(ok(:)), w, 'same');
    ys(~isfinite(ys)) = NaN;
    ys = reshape(ys, size(y));
end
