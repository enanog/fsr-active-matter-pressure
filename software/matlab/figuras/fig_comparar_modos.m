%% fig_comparar_modos.m  -  una magnitud agrupada por modo (AH / HO / AL): un punto por ensayo + media
% Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = 'todos';        % 'todos' | {'20260924', ...} part of the code | {} = pick from a list
magnitud = 'Phi_circulacion';   % any field of resumen_ensayo.m:
%   V_media, V_desvio, v_mediana_indiv, omega_media, omega_media_signo, robots_antihorario,
%   robots_horario, Phi_circulacion, Omega_grupo, pared_pct, alfa_msd, atasco_pct, n_atascos,
%   atasco_max_s, E_tras, E_rot, E_rot_sobre_E_tras, G_media, G_mediana, G_mediana_fluido,
%   G_mediana_atasco, asim_dG, curt_dG, rho_V_G
orden_modos = {'AH', 'HO', 'AL'};
nombres_modos = {'AH (antihorario)', 'HO (horario)', 'AL (aleatorio)'};   % axis labels in the same order
umbral   = 0.35;  suavizado_s = 30;
mostrar_media = true;      % horizontal line at the mean of each mode
etiquetas = true;          % trial date next to each point
linea_cero = true;
log_y = false;
lim_y = [];
titulo  = '';
texto_y = '\Phi (circulación, > 0 antihoraria)';
ancho_cm = 12;  alto_cm = 8;  fuente = 10;  tam_marcador = 7;
guardar = false;  archivo = 'comparar_modos';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, 'modo');
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, ['Por modo: ' magnitud]);
y = nan(1, numel(D));
for i = 1:numel(D)
    R = resumen_ensayo(D(i), umbral, suavizado_s);
    y(i) = R.(magnitud);
end
for k = 1:numel(orden_modos)
    sel = find(strcmp({D.modo}, orden_modos{k}));
    if isempty(sel), continue; end
    dx = linspace(-0.12, 0.12, numel(sel));  if numel(sel) == 1, dx = 0; end
    for j = 1:numel(sel)
        i = sel(j);
        plot(ax, k + dx(j), y(i), 'o', 'MarkerSize', tam_marcador, 'MarkerFaceColor', C(i, :), ...
             'MarkerEdgeColor', 'w', 'LineStyle', 'none');
        if etiquetas
            text(ax, k + dx(j), y(i), ['  ' D(i).etiqueta(1:5)], 'FontSize', fuente - 2, 'Color', [0.32 0.32 0.31]);
        end
    end
    if mostrar_media
        m = mean(y(sel), 'omitnan');
        plot(ax, k + [-0.25 0.25], [m m], '-', 'Color', C(sel(1), :), 'LineWidth', 2);
        fprintf('%s: media %.4g (%d ensayos)\n', orden_modos{k}, m, numel(sel));
    end
end
xlim(ax, [0.5, numel(orden_modos) + 0.5]);
set(ax, 'XTick', 1:numel(orden_modos), 'XTickLabel', nombres_modos, 'XGrid', 'off');
if linea_cero && ~log_y, plot(ax, xlim(ax), [0 0], 'Color', [0.45 0.45 0.43], 'LineWidth', 0.6); end
if log_y, set(ax, 'YScale', 'log'); end
if ~isempty(lim_y), ylim(ax, lim_y); end
ylabel(ax, texto_y);  title(ax, titulo);
if guardar, guardar_figura(fig, archivo, formatos); end
