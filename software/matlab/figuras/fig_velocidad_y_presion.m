%% fig_velocidad_y_presion.m  -  un ensayo: V media (arriba) y G (abajo) con el mismo eje de tiempo
% Two stacked panels instead of a double Y axis; jams shaded. Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayo      = '20260924_1600';   % ONE trial (part of the code)
suavizado_s = 30;                % moving average of both series [s]
crudo_gris  = true;              % raw V in grey behind
umbral      = 0.35;              % jam threshold [mm/s]; [] = no line and no shading
sombrear_atascos = true;
color_V = '#1baf7a';  color_G = '#2a78d6';  color_atasco = '#6250d6';
G_log   = true;                  % logarithmic G axis
lim_x = [];  lim_V = [];  lim_G = [];   % [] = automatic (V: up to 1.25 x the smoothed maximum)
titulo  = '';                    % '' = no title; 'auto' = trial name
texto_x = 't [min]';  texto_V = 'V_{media} [mm/s]';  texto_G = 'G [\muS]';
ancho_cm = 17;  alto_cm = 11;  fuente = 10;  grosor = 1.3;
guardar = false;  archivo = 'velocidad_y_presion';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos({ensayo});
if numel(D) > 1, error('"%s" coincide con %d ensayos: escribí más del código.', ensayo, numel(D)); end
c = colores_ensayos(repmat(D, 1, 3), {color_V, color_G, color_atasco});
[fig, ax1] = nueva_figura(ancho_cm, alto_cm, fuente, ['V y G - ' D.etiqueta]);
delete(ax1);
ax1 = subplot(2, 1, 1);  ax2 = subplot(2, 1, 2);
for a = [ax1 ax2]
    set(a, 'FontSize', fuente, 'Box', 'off', 'TickDir', 'out', 'XGrid', 'on', 'YGrid', 'on', ...
           'GridColor', [0.8 0.8 0.78]);
    hold(a, 'on');
end
t = D.t / 60;
if crudo_gris
    [x, y] = romper_huecos(t, D.V);
    plot(ax1, x, y, 'Color', [0.82 0.82 0.80], 'LineWidth', 0.5);
end
[x, y] = romper_huecos(t, suavizar(D.t, D.V, suavizado_s));
plot(ax1, x, y, 'Color', c(1, :), 'LineWidth', grosor);
if isempty(lim_V), lim_V = [0, 1.25 * max(y)]; end   % scale to the smoothed curve (raw spikes are clipped)
G = presion_en_cuadros(D, suavizado_s);
if G_log, G(G < 1e-3) = NaN; end
[x, y] = romper_huecos(t, G);
plot(ax2, x, y, 'Color', c(2, :), 'LineWidth', grosor);
if G_log, set(ax2, 'YScale', 'log'); end
if isempty(lim_x), lim_x = [0 t(end)]; end
xlim(ax1, lim_x);  xlim(ax2, lim_x);
if ~isempty(lim_V), ylim(ax1, lim_V); end
if ~isempty(lim_G), ylim(ax2, lim_G); end
if ~isempty(umbral)
    linea_referencia(ax1, 'h', umbral, sprintf('umbral %.2f', umbral));
    if sombrear_atascos
        A = atascos(D, umbral);
        sombrear_tramos(ax1, A.tramos / 60, c(3, :), 0.15);
        sombrear_tramos(ax2, A.tramos / 60, c(3, :), 0.15);
        fprintf('%s: atasco %.1f %% del tiempo (%d tramos, el más largo %.0f s)\n', ...
                D.etiqueta, 100 * A.fraccion, A.n, A.dur_max);
    end
end
ylabel(ax1, texto_V);  ylabel(ax2, texto_G);  xlabel(ax2, texto_x);
set(ax1, 'XTickLabel', []);
if strcmp(titulo, 'auto'), titulo = D.etiqueta; end
title(ax1, titulo);
fprintf('rho de Spearman entre V y G suavizadas: %.2f\n', spearman(suavizar(D.t, D.V, suavizado_s), G));
if guardar, guardar_figura(fig, archivo, formatos); end
