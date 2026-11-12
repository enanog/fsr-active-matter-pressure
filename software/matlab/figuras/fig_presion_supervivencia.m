%% fig_presion_supervivencia.m  -  P(G >= g): probabilidad de que la conductancia supere g
% Survival function of G over the samples inside the FSRScope mask (as in FSRScope and the poster).
% Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos    = {'20260824_1430', '20260824_1530', '20260824_1600'};   % part of the code; 'todos'; {} = pick from a list
nombres    = {};           % legend texts; {} = automatic. Tip: {'25 robots', '26 robots', '27 robots'}
colores    = {};           % {} = project palette | 'modo' | {'#2a78d6', ...}
normalizar = false;        % X = G / <G> (each trial divided by its mean): compares the shape only
log_x = true;  log_y = true;
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = '';              % '' = automatic
texto_y = 'P(G \geq g)';
leyenda = 'southwest';
ancho_cm = 17;  alto_cm = 9;  fuente = 10;  grosor = 1.4;
guardar = false;  archivo = 'presion_supervivencia';  formatos = {'pdf', 'png'};
%% ==================================================================

R = cargar_presion(ensayos);
C = colores_ensayos(R, colores);
if isempty(nombres), nombres = {R.etiqueta}; end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'Supervivencia de G');
h = [];
for i = 1:numel(R)
    [x, p] = supervivencia(presion_valida(R(i).P));
    if normalizar, x = x / mean(x); end
    if log_x, k = x > 0; x = x(k); p = p(k); end
    h(end + 1) = plot(ax, x, p, 'Color', C(i, :), 'LineWidth', grosor); %#ok<SAGROW>
end
if log_x, set(ax, 'XScale', 'log'); end
if log_y, set(ax, 'YScale', 'log'); end
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if isempty(texto_x)
    if normalizar, texto_x = 'g / \langle G \rangle'; else, texto_x = 'g [\muS]'; end
end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
