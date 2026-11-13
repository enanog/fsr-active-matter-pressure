%% fig_presion_vs_robots.m  -  G en función de la cantidad de robots (densidad), un punto por ensayo
% Median (or mean) of G inside the FSRScope mask, with the interquartile range as an error bar.
% Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {};   % {} = pick from a list of every trial (funciones/ensayos_base.m preselected) | 'todos' | {'...'} part of the code
excluir  = {'20260824_1400'};   % codes left out (e.g. the empty-room reference)
colores  = 'modo';         % 'modo' (AH blue, HO orange, AL green) | {} = per trial | {'#2a78d6', ...}
estadistico = 'mediana';   % 'mediana' | 'media'
barras   = true;           % interquartile range (25-75 %) as error bars
eje_x    = 'robots';       % 'robots' = N | 'fraccion' = area fraction N (D/2)^2 / R^2
diametro_robot_mm = 33;  diametro_recinto_mm = 185;
etiquetas = false;         % date and time of the measurement (AAAAMMDD_HHMM) next to each point (they overlap when several trials share N)
log_y    = true;
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = '';              % '' = automatic
texto_y = 'G [\muS]';
leyenda = 'southeast';
ancho_cm = 12;  alto_cm = 9;  fuente = 10;  tam_marcador = 7;
guardar = false;  archivo = 'presion_vs_robots';  formatos = {'pdf', 'png'};
%% ==================================================================

R = cargar_presion(ensayos);
quedan = true(size(R));
for k = 1:numel(excluir)
    quedan = quedan & cellfun(@isempty, strfind({R.codigo}, excluir{k}));
end
R = R(quedan);
C = colores_ensayos(R, colores);
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'G vs robots');
x = [R.robots];
if strcmp(eje_x, 'fraccion'), x = x * (diametro_robot_mm / diametro_recinto_mm) ^ 2; end
modos_vistos = {};  h = [];  txt = {};
for i = 1:numel(R)
    g = presion_valida(R(i).P);  g = sort(g(isfinite(g)));  n = numel(g);
    if strcmp(estadistico, 'media'), y = mean(g); else, y = median(g); end
    q1 = g(max(1, round(0.25 * n)));  q3 = g(max(1, round(0.75 * n)));
    if barras
        plot(ax, [x(i) x(i)], [q1 q3], '-', 'Color', C(i, :), 'LineWidth', 1, 'HandleVisibility', 'off');
    end
    hi = plot(ax, x(i), y, 'o', 'MarkerSize', tam_marcador, 'MarkerFaceColor', C(i, :), ...
              'MarkerEdgeColor', 'w', 'LineStyle', 'none');
    if etiquetas
        text(ax, x(i), y, ['  ' texto_tex(R(i).etiqueta(1:13))], 'FontSize', fuente - 2, 'Color', [0.32 0.32 0.31]);
    end
    m = R(i).modo;  if isempty(m), m = '-'; end
    if ischar(colores) && strcmpi(colores, 'modo')
        if ~any(strcmp(modos_vistos, m)), modos_vistos{end + 1} = m; h(end + 1) = hi; txt{end + 1} = m; end %#ok<SAGROW>
    else
        h(end + 1) = hi;  txt{end + 1} = R(i).etiqueta; %#ok<SAGROW>
    end
end
if log_y, set(ax, 'YScale', 'log'); end
dx = max(1e-9, max(x) - min(x));
xlim(ax, [min(x) - 0.15 * dx - 0.5 * (dx < 1e-6), max(x) + 0.25 * dx + 0.5 * (dx < 1e-6)]);
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if isempty(texto_x)
    if strcmp(eje_x, 'fraccion'), texto_x = 'fracción de área \phi'; else, texto_x = 'cantidad de robots N'; end
end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, txt, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
