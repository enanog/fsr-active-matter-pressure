function [Phi, Omega] = circulacion(D)
% CIRCULACION  Collective rotation about the centre of the enclosure, per frame (> 0 counter-clockwise):
%   Phi   order parameter: mean of sin(angle between position and velocity) over the moving robots
%         (|v| > 1 mm/s and r > 0.3 Rc); +1 = everyone orbiting counter-clockwise, 0 = no circulation
%   Omega angular velocity of the group [deg/s] = sum(x vy - y vx) / sum(r^2)
    r = hypot(D.X, D.Y);
    Rc = radio_contacto(D);
    L = D.X .* D.VY - D.Y .* D.VX;                  % z angular momentum per unit mass [mm^2/s]
    s = L ./ max(r .* hypot(D.VX, D.VY), 1e-12);
    s(~(D.S > 1 & r > 0.3 * Rc)) = NaN;
    Phi = mean_filas(s);
    ok = isfinite(L) & isfinite(r);
    L(~ok) = 0;  r2 = r .^ 2;  r2(~ok) = 0;
    Omega = sum(L, 2) ./ sum(r2, 2) * 180 / pi;
end

function m = mean_filas(A)
    ok = isfinite(A);
    A(~ok) = 0;
    m = sum(A, 2) ./ sum(ok, 2);
    m(sum(ok, 2) == 0) = NaN;
end
