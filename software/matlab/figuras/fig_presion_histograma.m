%% fig_presion_histograma.m  -  distribución de G (densidad de probabilidad)
% Over the samples inside the FSRScope mask. Log-spaced bins by default (G spans decades).
% Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {'20260924_1600', '20261030_1200', '20261030_1600'};  % part of the code; 'todos'; {} = pick from a list
nombres  = {};             % legend texts in the same order; {} = automatic
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
clases   = 40;             % fewer bins if the curve looks broken (empty bins are not drawn)
clases_log = true;         % log-spaced bins and log X axis (recommended for G)
G_minimo = 1e-3;           % smaller values are left out with log bins [uS]
log_y    = true;
normalizar = false;        % X = G / <G>
marcadores = false;
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = '';              % '' = automatic
texto_y = 'densidad de probabilidad [1/\muS]';
leyenda = 'northeast';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.3;
guardar = false;  archivo = 'presion_histograma';  formatos = {'pdf', 'png'};
%% ==================================================================

R = cargar_presion(ensayos);
C = colores_ensayos(R, colores);
if isempty(nombres), nombres = {R.etiqueta}; end
X = cell(1, numel(R));
for i = 1:numel(R)
    g = presion_valida(R(i).P);
    g = g(isfinite(g));
    if clases_log, g = g(g >= G_minimo); end      % log bins need G > 0
    if normalizar, g = g / mean(g); end
    X{i} = g;
end
lo = min(cellfun(@min, X));  hi = max(cellfun(@max, X));
if clases_log
    bordes = logspace(log10(lo), log10(hi), clases + 1);
    centros = sqrt(bordes(1:end - 1) .* bordes(2:end));
else
    bordes = linspace(lo, hi, clases + 1);
    centros = (bordes(1:end - 1) + bordes(2:end)) / 2;
end
marca = 'none';  if marcadores, marca = 'o'; end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'Histograma de G');
h = [];
for i = 1:numel(R)
    n = histc(X{i}, bordes);
    n = [n(1:end - 2); n(end - 1) + n(end)]';
    d = n ./ (numel(X{i}) * diff(bordes));          % density over the plotted samples
    d(d == 0) = NaN;
    h(end + 1) = plot(ax, centros, d, 'Color', C(i, :), 'LineWidth', grosor, 'Marker', marca, ...
                      'MarkerSize', 3, 'MarkerFaceColor', C(i, :)); %#ok<SAGROW>
end
if clases_log, set(ax, 'XScale', 'log'); end
if log_y, set(ax, 'YScale', 'log'); end
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if isempty(texto_x)
    if normalizar, texto_x = 'G / \langle G \rangle'; else, texto_x = 'G [\muS]'; end
end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
