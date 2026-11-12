%% fig_ccdf_velocidad.m  -  1 - F(v) = P(V >= v), opcionalmente de v / <v>
% Edit the SETTINGS block and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {'20260924_1600', '20261030_1200', '20261030_1600'};  % part of the code; {} = pick from a list
nombres  = {};             % legend texts in the same order; {} = automatic
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
fuente_v = 'media';        % 'media' = V of the group per frame | 'individual' = |v| of each robot
suavizado_s = 0;           % only for 'media'
normalizar = true;         % X = v / <v> (<v> = mean of each trial): compares the shape only
log_x = false;  log_y = true;
umbral = [];               % vertical line at the jam threshold [mm/s] (only if normalizar = false)
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = '';              % '' = automatic
texto_y = '1 - F';
leyenda = 'northeast';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.4;
guardar = false;  archivo = 'ccdf_velocidad';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, '1 - F(v)');
h = [];
for i = 1:numel(D)
    x = sort(muestras_velocidad(D(i), fuente_v, suavizado_s));
    p = (numel(x):-1:1)' / numel(x);                 % P(V >= x), never 0
    if normalizar, x = x / mean(x); end
    if log_x, k = x > 0; x = x(k); p = p(k); end
    h(end + 1) = plot(ax, x, p, 'Color', C(i, :), 'LineWidth', grosor); %#ok<SAGROW>
end
if log_x, set(ax, 'XScale', 'log'); end
if log_y, set(ax, 'YScale', 'log'); end
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if ~isempty(umbral) && ~normalizar, linea_referencia(ax, 'v', umbral, sprintf('umbral %.2f', umbral)); end
if isempty(texto_x)
    if normalizar, texto_x = 'v / \langle v \rangle'; else, texto_x = 'v [mm/s]'; end
end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
