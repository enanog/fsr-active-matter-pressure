%% fig_pdf_velocidad.m  -  densidad de probabilidad P(v)
% Edit the SETTINGS block and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {'20260924_1600', '20261030_1200', '20261030_1600'};  % part of the code; {} = pick from a list
nombres  = {};             % legend texts in the same order; {} = automatic
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
fuente_v = 'media';        % 'media' = V of the group per frame | 'individual' = |v| of each robot
suavizado_s = 0;           % only for 'media'
clases   = 60;
clases_log = false;        % logarithmically spaced bins (and log X axis): for power-law tails
log_y    = true;
marcadores = true;         % circles on the points
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = 'v [mm/s]';
texto_y = 'P(v) [s/mm]';
leyenda = 'northeast';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.2;
guardar = false;  archivo = 'pdf_velocidad';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
X = arrayfun(@(d) muestras_velocidad(d, fuente_v, suavizado_s), D, 'UniformOutput', false);
v_max = max(cellfun(@max, X));
if clases_log
    v_min = min(cellfun(@(x) min(x(x > 0)), X));
    bordes = logspace(log10(v_min), log10(v_max), clases + 1);
else
    bordes = linspace(0, v_max, clases + 1);
end
centros = (bordes(1:end - 1) + bordes(2:end)) / 2;
if clases_log, centros = sqrt(bordes(1:end - 1) .* bordes(2:end)); end
marca = 'none';  if marcadores, marca = 'o'; end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'P(v)');
h = [];
for i = 1:numel(D)
    n = histc(X{i}, bordes);
    n = [n(1:end - 2); n(end - 1) + n(end)]';
    p = n ./ (numel(X{i}) * diff(bordes));            % density: integrates to 1
    p(p == 0) = NaN;
    h(end + 1) = plot(ax, centros, p, '-', 'Color', C(i, :), 'LineWidth', grosor, 'Marker', marca, ...
                      'MarkerSize', 3, 'MarkerFaceColor', C(i, :)); %#ok<SAGROW>
end
if log_y, set(ax, 'YScale', 'log'); end
if clases_log, set(ax, 'XScale', 'log'); end
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
