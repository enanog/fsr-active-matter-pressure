function G = presion_en_cuadros(D, ventana_s)
% PRESION_EN_CUADROS  G [uS] at the instant of every video frame (t_sensor = offset + t_video),
% smoothed VENTANA_S seconds on the sensor grid (0 = raw), NaN outside the FSRScope mask or if there
% is no pressure log.
    if nargin < 2, ventana_s = 0; end
    if isempty(D.P), G = nan(size(D.t)); return; end
    g = presion_valida(D.P);
    gs = suavizar(D.P.t, g, ventana_s);
    gs(~D.P.mascara) = NaN;
    tf = D.P.offset + D.t;
    i = round((tf - D.P.t(1)) / D.P.paso) + 1;                % nearest grid sample (as Velocidades)
    G = nan(size(D.t));
    k = i >= 1 & i <= numel(gs);
    G(k) = gs(i(k));
end
