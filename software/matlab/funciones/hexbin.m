function H = hexbin(x, y, nx, ny, lim_x, lim_y)
% HEXBIN  Count the points (x, y) in a grid of hexagons (same algorithm as matplotlib's hexbin).
%   nx = hexagons across lim_x; ny = rows of the grid over lim_y. For regular hexagons on screen use
%   ny = nx * (panel height / panel width) / sqrt(3).
%   H.cx, H.cy  centres of the non-empty hexagons;  H.n  points in each one
%   H.dx, H.dy  vertex offsets (1x6): vertices of hexagon k = [H.cx(k) + H.dx; H.cy(k) + H.dy]
% Two interleaved lattices, (i, j) and (i + 1/2, j + 1/2) in cell units; every point goes to the nearer
% centre with the metric du^2 + 3 dw^2, which makes the cells hexagons.
    ok = isfinite(x) & isfinite(y) & x >= lim_x(1) & x <= lim_x(2) & y >= lim_y(1) & y <= lim_y(2);
    x = x(ok);  y = y(ok);
    sx = diff(lim_x) / nx;  sy = diff(lim_y) / ny;
    u = (x(:) - lim_x(1)) / sx;  w = (y(:) - lim_y(1)) / sy;
    i1 = round(u);  j1 = round(w);
    i2 = floor(u);  j2 = floor(w);
    d1 = (u - i1) .^ 2 + 3 * (w - j1) .^ 2;
    d2 = (u - i2 - 0.5) .^ 2 + 3 * (w - j2 - 0.5) .^ 2;
    ki = 2 * i1;  kj = 2 * j1;                         % key in half cells: lattice 1 even, lattice 2 odd
    b = d2 < d1;
    ki(b) = 2 * i2(b) + 1;  kj(b) = 2 * j2(b) + 1;
    if isempty(ki)
        claves = zeros(0, 2);  H.n = zeros(0, 1);
    else
        [claves, ~, g] = unique([ki kj], 'rows');
        H.n = accumarray(g, 1);
    end
    H.cx = lim_x(1) + claves(:, 1) / 2 * sx;
    H.cy = lim_y(1) + claves(:, 2) / 2 * sy;
    H.dx = sx * [0.5 0.5 0 -0.5 -0.5 0];
    H.dy = sy / 3 * [-0.5 0.5 1 0.5 -0.5 -1];
end
