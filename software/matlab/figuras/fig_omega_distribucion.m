%% fig_omega_distribucion.m  -  distribución de la velocidad angular omega (con signo)
% Observed robots and frames; > 0 counter-clockwise. Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {'20260924_1600', '20261030_1200', '20261030_1600'};  % part of the code; 'todos'; {} = pick from a list
nombres  = {};             % legend texts in the same order; {} = automatic
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
valor_absoluto = false;    % distribution of |omega| instead of omega
rango    = 60;             % plotted range [deg/s]: -rango..rango (or 0..rango with |omega|)
clases   = 60;
log_y    = false;
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = '';              % '' = automatic
texto_y = 'densidad de probabilidad [s/°]';
leyenda = 'northeast';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.3;
guardar = false;  archivo = 'omega_distribucion';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
if valor_absoluto, bordes = linspace(0, rango, clases + 1); else, bordes = linspace(-rango, rango, clases + 1); end
centros = (bordes(1:end - 1) + bordes(2:end)) / 2;
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'Distribucion de omega');
h = [];
for i = 1:numel(D)
    w = D(i).Wr(D(i).OBS);  w = w(isfinite(w));
    if valor_absoluto, w = abs(w); end
    n = histc(min(max(w, bordes(1)), bordes(end) - 1e-9), bordes);
    n = [n(1:end - 2); n(end - 1) + n(end)]';
    p = n ./ (numel(w) * diff(bordes));
    if log_y, p(p == 0) = NaN; end
    h(end + 1) = plot(ax, centros, p, 'Color', C(i, :), 'LineWidth', grosor); %#ok<SAGROW>
    fprintf('%s: omega media %.2f °/s, %.0f %% del tiempo antihorario\n', D(i).etiqueta, mean(D(i).Wr(D(i).OBS & isfinite(D(i).Wr))), ...
            100 * mean(D(i).Wr(D(i).OBS & isfinite(D(i).Wr)) > 0));
end
if ~valor_absoluto
    plot(ax, [0 0], ylim(ax), 'Color', [0.45 0.45 0.43], 'LineWidth', 0.6, 'HandleVisibility', 'off');
end
if log_y, set(ax, 'YScale', 'log'); end
xlim(ax, bordes([1 end]));
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if isempty(texto_x)
    if valor_absoluto, texto_x = '|\omega| [°/s]'; else, texto_x = '\omega [°/s] (> 0 antihorario)'; end
end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
