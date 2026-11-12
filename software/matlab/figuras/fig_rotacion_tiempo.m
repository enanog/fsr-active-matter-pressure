%% fig_rotacion_tiempo.m  -  <|omega|> (giro propio medio de los robots) vs tiempo
% Edit the SETTINGS block and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos     = {'20260924_1600', '20261030_1200', '20261030_1600'};  % part of the code; {} = pick from a list
nombres     = {};          % legend texts in the same order; {} = automatic
colores     = {};          % {} = project palette | 'modo' | {'#2a78d6', [1 0 0], ...}
suavizado_s = 30;          % moving average [s]; 0 = raw data
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = 't [min]';
texto_y = '\langle|\omega|\rangle [°/s]';
leyenda = 'northeast';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.4;
guardar = false;  archivo = 'rotacion_tiempo';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'Rotacion vs tiempo');
h = [];
for i = 1:numel(D)
    [x, y] = romper_huecos(D(i).t / 60, suavizar(D(i).t, D(i).W, suavizado_s));
    h(end + 1) = plot(ax, x, y, 'Color', C(i, :), 'LineWidth', grosor);
end
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
