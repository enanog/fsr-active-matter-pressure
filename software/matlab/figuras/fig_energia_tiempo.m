%% fig_energia_tiempo.m  -  energía cinética del conjunto vs tiempo
% Translation N<½v²> and rotation N<½kR²omega²>. Edit the SETTINGS block and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos     = ensayos_base();   % {} = pick from a list of every trial (funciones/ensayos_base.m preselected) | 'todos' | {'...'} part of the code
nombres     = {};          % legend texts in the same order; {} = automatic
colores     = {};          % {} = project palette | 'modo' | {'#2a78d6', ...}
que         = 'total';     % 'total' | 'traslacion' | 'rotacion' | 'ambas' (solid = translation, dotted = rotation)
masa_g      = 0;           % robot mass [g]; 0 = energy per unit mass [uJ/kg]
k_inercia   = 0.5;         % I = k m R^2 (0.5 = uniform disc, an assumption)
diametro_mm = 33;          % robot diameter
suavizado_s = 30;          % moving average [s]
escala_log  = false;       % logarithmic Y axis
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = 't [min]';
texto_y = '';              % '' = automatic ('E/m [uJ/kg]' or 'E [nJ]')
leyenda = 'northeast';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.4;
guardar = false;  archivo = 'energia_tiempo';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'Energia cinetica');
h = [];
for i = 1:numel(D)
    [Et, Er, unidad] = energia(D(i), masa_g, k_inercia, diametro_mm);
    switch que
        case 'total',      series = {Et + Er};  estilos = {'-'};
        case 'traslacion', series = {Et};       estilos = {'-'};
        case 'rotacion',   series = {Er};       estilos = {'-'};
        case 'ambas',      series = {Et, Er};   estilos = {'-', ':'};
        otherwise, error('que = total | traslacion | rotacion | ambas');
    end
    for s = 1:numel(series)
        [x, y] = romper_huecos(D(i).t / 60, suavizar(D(i).t, series{s}, suavizado_s));
        hs = plot(ax, x, y, estilos{s}, 'Color', C(i, :), 'LineWidth', grosor);
        if s == 1, h(end + 1) = hs; else, set(hs, 'HandleVisibility', 'off'); end
    end
end
if escala_log, set(ax, 'YScale', 'log'); end
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if isempty(texto_y), texto_y = unidad; end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
