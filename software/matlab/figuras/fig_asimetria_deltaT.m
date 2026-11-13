%% fig_asimetria_deltaT.m  -  asimetría (y/o curtosis) de dG en función de la ventana dT
% Same sweep as FSRScope and the poster: for each dT, skewness of dG = G(t) - G(t - dT).
% Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = ensayos_base();   % {} = pick from a list of every trial (funciones/ensayos_base.m preselected) | 'todos' | {'...'} part of the code
nombres  = {};             % legend texts; {} = automatic. Tip: {'25 robots', '26 robots', '27 robots'}
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
que      = 'asimetria';    % 'asimetria' | 'curtosis' | 'ambas' (two panels)
deltaT_max  = 15;          % largest window [s]
paso_deltaT = 0.05;        % sweep step [s] (0.05 = every sample, as FSRScope; larger = faster)
linea_cero = true;
lim_x = [];  lim_y = [];  lim_y2 = [];   % lim_y2: kurtosis panel when que = 'ambas'
titulo  = '';
texto_x = '\DeltaT [s]';
texto_asim = 'asimetría de \DeltaG';
texto_curt = 'curtosis de \DeltaG';
leyenda = 'best';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.4;
guardar = true;  archivo = 'asimetria_deltaT';  formatos = {'png'};
%% ==================================================================

R = cargar_presion(ensayos);
C = colores_ensayos(R, colores);
if isempty(nombres), nombres = {R.etiqueta}; end
dobles = strcmp(que, 'ambas');
[fig, ax0] = nueva_figura(ancho_cm, alto_cm * (1 + 0.6 * dobles), fuente, 'Momentos de Delta G');
if dobles
    delete(ax0);
    ax = [subplot(2, 1, 1), subplot(2, 1, 2)];
    for a = ax
        set(a, 'FontSize', fuente, 'Box', 'off', 'TickDir', 'out', 'XGrid', 'on', 'YGrid', 'on', ...
               'GridColor', [0.8 0.8 0.78]);
        hold(a, 'on');
    end
else
    ax = ax0;
end
h = [];
for i = 1:numel(R)
    [dT, s, k] = momentos_vs_deltaT(R(i).P, deltaT_max, paso_deltaT);
    switch que
        case 'asimetria', h(end + 1) = plot(ax(1), dT, s, 'Color', C(i, :), 'LineWidth', grosor); %#ok<SAGROW>
        case 'curtosis',  h(end + 1) = plot(ax(1), dT, k, 'Color', C(i, :), 'LineWidth', grosor); %#ok<SAGROW>
        case 'ambas'
            h(end + 1) = plot(ax(1), dT, s, 'Color', C(i, :), 'LineWidth', grosor); %#ok<SAGROW>
            plot(ax(2), dT, k, 'Color', C(i, :), 'LineWidth', grosor);
        otherwise, error('que = asimetria | curtosis | ambas');
    end
end
for a = ax
    if ~isempty(lim_x), xlim(a, lim_x); else, xlim(a, [0 deltaT_max]); end
    if linea_cero, plot(a, xlim(a), [0 0], 'Color', [0.45 0.45 0.43], 'LineWidth', 0.6, 'HandleVisibility', 'off'); end
end
if ~isempty(lim_y), ylim(ax(1), lim_y); end
if dobles && ~isempty(lim_y2), ylim(ax(2), lim_y2); end
switch que
    case 'asimetria', ylabel(ax(1), texto_asim);
    case 'curtosis',  ylabel(ax(1), texto_curt);
    case 'ambas',     ylabel(ax(1), texto_asim);  ylabel(ax(2), texto_curt);  set(ax(1), 'XTickLabel', []);
end
xlabel(ax(end), texto_x);  title(ax(1), titulo);
poner_leyenda(ax(1), h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
