%% fig_histograma_velocidad.m  -  histograma de velocidades (fracción de las muestras)
% Same bins for every trial so the curves are comparable. Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = ensayos_base();   % {} = pick from a list of every trial (funciones/ensayos_base.m preselected) | 'todos' | {'...'} part of the code
nombres  = {};             % legend texts in the same order; {} = automatic
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
fuente_v = 'media';        % 'media' = V of the group per frame | 'individual' = |v| of each robot
suavizado_s = 0;           % only for 'media': histogram of the smoothed V (changes the width!)
clases   = 60;             % number of bins
v_max    = [];             % right edge of the last bin [mm/s]; [] = largest sample
estilo   = 'escalon';      % 'escalon' (outline) | 'barras' (filled, translucent)
escala_log = false;        % logarithmic Y axis
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = 'v [mm/s]';
texto_y = 'fracción de las muestras';
leyenda = 'northeast';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.3;
guardar = false;  archivo = 'histograma_velocidad';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
X = arrayfun(@(d) muestras_velocidad(d, fuente_v, suavizado_s), D, 'UniformOutput', false);
if isempty(v_max), v_max = max(cellfun(@max, X)); end
bordes = linspace(0, v_max, clases + 1);
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'Histograma de velocidades');
h = [];
for i = 1:numel(D)
    n = histc(X{i}, bordes);                       % last element counts x == v_max
    n = [n(1:end - 2); n(end - 1) + n(end)]' / numel(X{i});
    if strcmp(estilo, 'barras')
        h(end + 1) = bar(ax, bordes(1:end - 1) + diff(bordes) / 2, n, 1, 'FaceColor', C(i, :), ...
                         'EdgeColor', 'none', 'FaceAlpha', 0.35); %#ok<SAGROW>
    else
        h(end + 1) = stairs(ax, bordes, [n n(end)], 'Color', C(i, :), 'LineWidth', grosor); %#ok<SAGROW>
    end
end
if escala_log, set(ax, 'YScale', 'log'); end
xlim(ax, [0 v_max]);
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
