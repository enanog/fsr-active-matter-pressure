%% fig_circulacion_tiempo.m  -  circulación colectiva alrededor del centro vs tiempo
% Phi: +1 = everyone orbiting counter-clockwise, -1 clockwise, 0 no net circulation (moving robots only).
% Omega: angular velocity of the whole group [deg/s]. Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {'20260924_1600', '20261030_1200', '20261030_1600'};  % part of the code; 'todos'; {} = pick from a list
nombres  = {};             % legend texts in the same order; {} = automatic
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
que      = 'Phi';          % 'Phi' (order parameter, -1..1) | 'Omega' (deg/s)
suavizado_s = 60;          % moving average [s]
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = 't [min]';
texto_y = '';              % '' = automatic
leyenda = 'northeast';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.4;
guardar = false;  archivo = 'circulacion_tiempo';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'Circulacion');
h = [];
for i = 1:numel(D)
    [Phi, Omega] = circulacion(D(i));
    if strcmp(que, 'Omega'), y = Omega; else, y = Phi; end
    fprintf('%s: %s medio = %.3f\n', D(i).etiqueta, que, mean(y(isfinite(y))));
    [x, y] = romper_huecos(D(i).t / 60, suavizar(D(i).t, y, suavizado_s));
    h(end + 1) = plot(ax, x, y, 'Color', C(i, :), 'LineWidth', grosor); %#ok<SAGROW>
end
plot(ax, xlim(ax), [0 0], 'Color', [0.45 0.45 0.43], 'LineWidth', 0.6, 'HandleVisibility', 'off');
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if isempty(texto_y)
    if strcmp(que, 'Omega'), texto_y = '\Omega del grupo [°/s] (> 0 antihorario)'; else, texto_y = '\Phi (> 0 antihorario)'; end
end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
