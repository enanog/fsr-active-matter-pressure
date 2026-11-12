%% fig_velocidad_tiempo.m  -  V media del conjunto vs tiempo (una curva por ensayo)
% Edit the SETTINGS block and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos     = {'20260924_1600', '20261030_1200', '20261030_1600'};  % part of the code; {} = pick from a list
nombres     = {};          % legend texts in the same order; {} = automatic ('24/09 16:00 · 22AH')
colores     = {};          % {} = project palette | 'modo' | {'#2a78d6', [1 0 0], 'k', ...}
estadistico = 'media';     % one speed per frame: 'media' | 'mediana' | 'p90' (report mobility index) | 'p10'
suavizado_s = 30;          % moving average [s]; 0 = raw data
crudo_gris  = false;       % also draw the raw series in grey behind
umbral      = 0.35;        % jam threshold line [mm/s]; [] = no line
sombrear_atascos = false;  % shade the jams of each trial in its colour
lim_x = [];  lim_y = [];   % axis limits, e.g. [0 60]; [] = automatic
titulo  = '';              % '' = no title
texto_x = 't [min]';
texto_y = 'V_{media} [mm/s]';
leyenda = 'northeast';     % 'best', 'northwest', 'eastoutside', 'southoutside', 'ninguna', ...
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.4;
guardar = false;  archivo = 'velocidad_tiempo';  formatos = {'pdf', 'png'};   % informes/figuras/matlab/
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'V media vs tiempo');
h = [];
for i = 1:numel(D)
    v = rapidez_conjunto(D(i), estadistico);
    if crudo_gris
        [x, y] = romper_huecos(D(i).t / 60, v);
        plot(ax, x, y, 'Color', [0.82 0.82 0.80], 'LineWidth', 0.5, 'HandleVisibility', 'off');
    end
    [x, y] = romper_huecos(D(i).t / 60, suavizar(D(i).t, v, suavizado_s));
    h(end + 1) = plot(ax, x, y, 'Color', C(i, :), 'LineWidth', grosor);
end
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if sombrear_atascos
    for i = 1:numel(D)
        A = atascos(D(i), umbral);
        sombrear_tramos(ax, A.tramos / 60, C(i, :), 0.12);
    end
end
if ~isempty(umbral), linea_referencia(ax, 'h', umbral, sprintf('umbral %.2f', umbral)); end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
