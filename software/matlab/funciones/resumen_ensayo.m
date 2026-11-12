function R = resumen_ensayo(D, umbral, suavizado_s, masa_g)
% RESUMEN_ENSAYO  Mean values of one trial (one row of the summary table / one bar / one point).
%   umbral [mm/s] and suavizado_s [s] as in the other figures (0.35 and 30 by default).
    if nargin < 2 || isempty(umbral), umbral = 0.35; end
    if nargin < 3 || isempty(suavizado_s), suavizado_s = 30; end
    if nargin < 4, masa_g = 0; end
    A = atascos(D, umbral);
    [Et, Er] = energia(D, masa_g);
    G = presion_en_cuadros(D, 0);
    Gs = presion_en_cuadros(D, suavizado_s);
    ok = isfinite(G);
    R.ensayo            = D.etiqueta;
    R.modo              = D.modo;
    R.minutos           = (D.t(end) - D.t(1)) / 60;
    R.V_media           = mean(D.V, 'omitnan');
    R.V_desvio          = std(D.V(isfinite(D.V)));
    R.v_mediana_indiv   = mediana_o_nan(D.v_ind);
    R.omega_media       = mean(D.W, 'omitnan');
    R.atasco_pct        = 100 * A.fraccion;
    R.n_atascos         = A.n;
    R.atasco_max_s      = A.dur_max;
    R.E_tras            = mean(Et, 'omitnan');
    R.E_rot             = mean(Er, 'omitnan');
    R.E_rot_sobre_E_tras = R.E_rot / R.E_tras;
    R.G_media           = mean(G(ok));
    if ~any(ok), R.G_media = NaN; end
    R.G_mediana         = mediana_o_nan(G(ok));
    R.G_mediana_fluido  = mediana_o_nan(G(ok & ~A.mascara));
    R.G_mediana_atasco  = mediana_o_nan(G(ok & A.mascara));
    R.rho_V_G           = spearman(suavizar(D.t, D.V, suavizado_s), Gs);
    % rotation, wall and diffusion (as comparar_modos.py / comparar_ensayos.py)
    r = hypot(D.X, D.Y);
    Rc = radio_contacto(D);
    wmean = media_columnas(D.Wr);                  % mean omega of each robot [deg/s]
    wo = D.Wr(D.OBS);  wo = wo(isfinite(wo));
    [Phi, Omega] = circulacion(D);
    [~, ~, alfa] = desplazamiento_cuadratico(D);
    R.omega_media_signo = mean(wo);                % > 0 counter-clockwise
    R.robots_antihorario = nnz(wmean > 0.5);
    R.robots_horario    = nnz(wmean < -0.5);
    R.Phi_circulacion   = mean(Phi(isfinite(Phi)));
    R.Omega_grupo       = mean(Omega(isfinite(Omega)));
    pared = r >= Rc - 33 / 2;
    R.pared_pct         = 100 * mean(pared(isfinite(r)));
    R.alfa_msd          = alfa;
    if isempty(D.P)
        R.asim_dG = NaN;  R.curt_dG = NaN;
    else
        [R.asim_dG, R.curt_dG] = momentos(delta_g(D.P, D.P.deltaT_fijo));
    end
end

function m = mediana_o_nan(x)
    if isempty(x), m = NaN; else, m = median(x); end
end

function m = media_columnas(A)
    ok = isfinite(A);
    A(~ok) = 0;
    m = sum(A, 1) ./ sum(ok, 1);
    m(sum(ok, 1) == 0) = NaN;
end
