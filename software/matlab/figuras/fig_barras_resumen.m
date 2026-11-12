%% fig_barras_resumen.m  -  una magnitud por ensayo, en barras (ej. % de tiempo en atasco)
% Edit the SETTINGS block and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = 'todos';        % 'todos' | {'20260924', ...} part of the code | {} = pick from a list
nombres  = {};             % bar labels in the same order; {} = automatic
colores  = 'modo';         % 'modo' (AH blue, HO orange, AL green) | {} = per trial | {'#2a78d6', ...}
magnitud = 'atasco_pct';   % any field of resumen_ensayo.m:
%   V_media, V_desvio, v_mediana_indiv, omega_media, omega_media_signo, robots_antihorario,
%   robots_horario, Phi_circulacion, Omega_grupo, pared_pct, alfa_msd, atasco_pct, n_atascos,
%   atasco_max_s, E_tras, E_rot, E_rot_sobre_E_tras, G_media, G_mediana, G_mediana_fluido,
%   G_mediana_atasco, asim_dG, curt_dG, rho_V_G
umbral   = 0.35;           % jam threshold [mm/s] (for the jam quantities)
suavizado_s = 30;
valores_sobre_barras = true;
log_y = false;
lim_y = [];
titulo  = '';
texto_y = 'tiempo en atasco [%]';
horizontal = false;        % horizontal bars (long labels)
ancho_cm = 17;  alto_cm = 8;  fuente = 10;
guardar = false;  archivo = 'barras_resumen';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
y = zeros(1, numel(D));
for i = 1:numel(D)
    R = resumen_ensayo(D(i), umbral, suavizado_s);
    y(i) = R.(magnitud);
end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, magnitud);
for i = 1:numel(D)
    if horizontal
        barh(ax, i, y(i), 0.7, 'FaceColor', C(i, :), 'EdgeColor', 'none');
    else
        bar(ax, i, y(i), 0.7, 'FaceColor', C(i, :), 'EdgeColor', 'none');
    end
    if valores_sobre_barras
        if horizontal
            text(ax, y(i), i, sprintf(' %.3g', y(i)), 'VerticalAlignment', 'middle', 'FontSize', fuente - 1);
        else
            text(ax, i, y(i), sprintf('%.3g', y(i)), 'HorizontalAlignment', 'center', ...
                 'VerticalAlignment', 'bottom', 'FontSize', fuente - 1);
        end
    end
end
if horizontal
    set(ax, 'YTick', 1:numel(D), 'YTickLabel', nombres, 'YDir', 'reverse', 'YGrid', 'off');
    xlabel(ax, texto_y);
    if log_y, set(ax, 'XScale', 'log'); end
    if ~isempty(lim_y), xlim(ax, lim_y); end
else
    set(ax, 'XTick', 1:numel(D), 'XTickLabel', nombres, 'XGrid', 'off');
    try, set(ax, 'XTickLabelRotation', 30); catch, end
    ylabel(ax, texto_y);
    if log_y, set(ax, 'YScale', 'log'); end
    if ~isempty(lim_y), ylim(ax, lim_y); end
end
title(ax, titulo);
if guardar, guardar_figura(fig, archivo, formatos); end
