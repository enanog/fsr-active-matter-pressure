function H = histograma2d(x, y, nx, ny, lim_x, lim_y)
% HISTOGRAMA2D  Count the points (x, y) in NX x NY rectangles over lim_x, lim_y (what histcounts2 /
% histogram2 do, also in Octave). Same output as hexbin, so both draw with the same code:
%   H.cx, H.cy  centres of the non-empty rectangles;  H.n  points in each one
%   H.dx, H.dy  vertex offsets (1x4): vertices of rectangle k = [H.cx(k) + H.dx; H.cy(k) + H.dy]
    ok = isfinite(x) & isfinite(y) & x >= lim_x(1) & x <= lim_x(2) & y >= lim_y(1) & y <= lim_y(2);
    x = x(ok);  y = y(ok);
    sx = diff(lim_x) / nx;  sy = diff(lim_y) / ny;
    i = min(nx - 1, floor((x(:) - lim_x(1)) / sx));      % the right / top edge belongs to the last cell
    j = min(ny - 1, floor((y(:) - lim_y(1)) / sy));
    if isempty(i)
        claves = zeros(0, 2);  H.n = zeros(0, 1);
    else
        [claves, ~, g] = unique([i j], 'rows');
        H.n = accumarray(g, 1);
    end
    H.cx = lim_x(1) + (claves(:, 1) + 0.5) * sx;
    H.cy = lim_y(1) + (claves(:, 2) + 0.5) * sy;
    H.dx = sx * [-0.5 0.5 0.5 -0.5];
    H.dy = sy * [-0.5 -0.5 0.5 0.5];
end
