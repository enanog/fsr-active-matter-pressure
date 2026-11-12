%% tabla_presion.m  -  valores de presión de cada registro (en la consola y en CSV)
% Over the samples inside the FSRScope mask. Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = 'todos';        % 'todos' | {'20260824', ...} part of the code | {} = pick from a list
deltaT_s = 2.5;            % window for the skewness / kurtosis of dG [s]
guardar_csv = false;  archivo = 'presion_ensayos_matlab.csv';   % -> informes/figuras/matlab/
%% ==================================================================

R = cargar_presion(ensayos);
cols = {'robots', 'minutos', 'G_media', 'G_desvio', 'G_mediana', 'G_p90', 'saturado_pct', ...
        'asim_dG', 'curt_dG', 'K_uS_cuenta', 'R_FB_ohm', 'desfase_s'};
V = nan(numel(R), numel(cols));
for i = 1:numel(R)
    P = R(i).P;
    g = presion_valida(P);  g = sort(g(isfinite(g)));
    [a, c] = momentos(delta_g(P, deltaT_s));
    V(i, :) = [R(i).robots, nnz(P.mascara) * P.paso / 60, mean(g), std(g), median(g), ...
               g(max(1, round(0.9 * numel(g)))), 100 * mean(P.sat(P.mascara)), a, c, P.K, P.r_feedback, P.offset];
end
ancho = max(11, cellfun(@numel, cols) + 2);
fprintf('\n%-22s', 'registro');
for c = 1:numel(cols), fprintf('%*s', ancho(c), cols{c}); end
fprintf('\n');
for i = 1:numel(R)
    fprintf('%-22s', R(i).etiqueta);
    for c = 1:numel(cols), fprintf('%*.4g', ancho(c), V(i, c)); end
    fprintf('\n');
end
fprintf('(asimetría y curtosis de dG con dT = %g s; desfase = t_sensor - t_video)\n', deltaT_s);
if guardar_csv
    carpeta = fullfile(raiz_proyecto(), 'informes', 'figuras', 'matlab');
    if ~isfolder(carpeta), mkdir(carpeta); end
    f = fopen(fullfile(carpeta, archivo), 'w');
    fprintf(f, 'codigo,registro,modo,%s\n', strjoin(cols, ','));
    for i = 1:numel(R)
        fprintf(f, '%s,%s,%s', R(i).codigo, R(i).etiqueta, R(i).modo);
        fprintf(f, ',%.6g', V(i, :));
        fprintf(f, '\n');
    end
    fclose(f);
    fprintf('Guardada: %s\n', fullfile(carpeta, archivo));
end
