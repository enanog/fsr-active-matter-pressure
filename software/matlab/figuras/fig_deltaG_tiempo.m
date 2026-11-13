%% fig_deltaG_tiempo.m  -  dG(t) = G(t) - G(t - dT): cambios de presión en una ventana dT
% Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {};   % {} = pick from a list of every trial (funciones/ensayos_base.m preselected) | 'todos' | {'...'} part of the code
nombres  = {};             % legend texts in the same order; {} = automatic
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
deltaT_s = 2.5;            % window [s]; [] = the one saved in FSRScope for each trial
eje_tiempo = 'video';      % 'video' | 'sensor'
paneles  = true;           % one panel per trial (true) or all on the same axes (false)
lim_x = [];  lim_y = [];
titulo  = '';              % '' = no title; 'auto' = trial names in each panel
texto_x = 't [min]';
texto_y = '\DeltaG [\muS]';
leyenda = 'northeast';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 0.6;
guardar = false;  archivo = 'deltaG_tiempo';  formatos = {'pdf', 'png'};
%% ==================================================================

R = cargar_presion(ensayos);
C = colores_ensayos(R, colores);
if isempty(nombres), nombres = {R.etiqueta}; end
n = numel(R);
if ~paneles, n_pan = 1; else, n_pan = n; end
[fig, ax0] = nueva_figura(ancho_cm, alto_cm * max(1, 0.6 * n_pan), fuente, 'Delta G vs tiempo');
delete(ax0);
h = [];
for i = 1:n
    if paneles || i == 1
        ax = subplot(n_pan, 1, min(i, n_pan));
        set(ax, 'FontSize', fuente, 'Box', 'off', 'TickDir', 'out', 'XGrid', 'on', 'YGrid', 'on', ...
                'GridColor', [0.8 0.8 0.78]);
        hold(ax, 'on');
    end
    P = R(i).P;
    dT = deltaT_s;  if isempty(dT), dT = P.deltaT_fijo; end
    t = P.t;  if strcmp(eje_tiempo, 'video'), t = t - P.offset; end
    dG = delta_g(P, dT);
    if strcmp(eje_tiempo, 'video'), dG(t < 0) = NaN; end
    h(end + 1) = plot(ax, t / 60, dG, 'Color', C(i, :), 'LineWidth', grosor); %#ok<SAGROW>
    plot(ax, [min(t) max(t)] / 60, [0 0], 'Color', [0.4 0.4 0.4], 'LineWidth', 0.5, 'HandleVisibility', 'off');
    if ~isempty(lim_x), xlim(ax, lim_x); elseif strcmp(eje_tiempo, 'video'), xlim(ax, [0 max(t) / 60]); end
    if ~isempty(lim_y), ylim(ax, lim_y); end
    ylabel(ax, texto_y);
    if paneles
        if strcmp(titulo, 'auto'), title(ax, sprintf('%s  (\\DeltaT = %g s)', texto_tex(nombres{i}), dT)); end
        if i < n, set(ax, 'XTickLabel', []); end
    end
end
xlabel(ax, texto_x);
if ~paneles
    if ~strcmp(titulo, 'auto'), title(ax, titulo); end
    poner_leyenda(ax, h, nombres, leyenda);
elseif ~strcmp(titulo, 'auto') && ~isempty(titulo)
    title(subplot(n_pan, 1, 1), titulo);
end
if guardar, guardar_figura(fig, archivo, formatos); end
