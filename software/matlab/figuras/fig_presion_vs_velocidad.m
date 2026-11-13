%% fig_presion_vs_velocidad.m  -  G mediana por clase de V media (más velocidad <-> menos presión?)
% Both series smoothed the same; classes with few frames are left empty. Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {};   % {} = pick from a list of every trial (funciones/ensayos_base.m preselected) | 'todos' | {'...'} part of the code
nombres  = {};             % legend texts in the same order; {} = automatic (adds rho)
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
suavizado_s = 15;          % moving average of V and G [s]
clases      = 25;          % V classes (same edges for every trial)
min_cuadros = 30;          % a class needs at least this many frames (30 = 10 s)
banda       = false;        % shaded interquartile range (25-75 %)
nube        = false;       % also every frame as a faint point
mostrar_rho = true;        % Spearman correlation in the legend
log_y = true;
umbral = 0.35;             % vertical line at the jam threshold [mm/s]; [] = none
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = 'V_{media} [mm/s]';
texto_y = 'G [\muS]';
leyenda = 'northeast';
ancho_cm = 17;  alto_cm = 9;  fuente = 10;  grosor = 1.4;
guardar = false;  archivo = 'presion_vs_velocidad';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
V = cell(1, numel(D));  G = V;
for i = 1:numel(D)
    V{i} = suavizar(D(i).t, D(i).V, suavizado_s);
    G{i} = presion_en_cuadros(D(i), suavizado_s);
    if log_y, G{i}(G{i} < 1e-3) = NaN; end
end
v_max = max(cellfun(@(v, g) max(v(isfinite(g))), V, G));
bordes = linspace(0, v_max, clases + 1);
centros = (bordes(1:end - 1) + bordes(2:end)) / 2;
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'G vs V media');
h = [];  txt = {};
for i = 1:numel(D)
    ok = isfinite(V{i}) & isfinite(G{i});
    if ~any(ok), fprintf('%s: sin registro de G\n', D(i).codigo); continue; end
    v = V{i}(ok);  g = G{i}(ok);
    [~, k] = histc(v, bordes);  k(k == clases + 1) = clases;
    med = nan(1, clases);  q1 = med;  q3 = med;
    for j = 1:clases
        gj = g(k == j);
        if numel(gj) >= min_cuadros
            s = sort(gj);  n = numel(s);
            med(j) = median(s);  q1(j) = s(max(1, round(0.25 * n)));  q3(j) = s(max(1, round(0.75 * n)));
        end
    end
    if nube
        plot(ax, v, g, '.', 'Color', 0.25 + 0.75 * C(i, :), 'MarkerSize', 2, 'HandleVisibility', 'off');
    end
    if banda
        b = isfinite(med);
        fill(ax, [centros(b) fliplr(centros(b))], [q1(b) fliplr(q3(b))], C(i, :), ...
             'FaceAlpha', 0.15, 'EdgeColor', 'none', 'HandleVisibility', 'off');
    end
    h(end + 1) = plot(ax, centros, med, '-o', 'Color', C(i, :), 'LineWidth', grosor, ...
                      'MarkerSize', 4, 'MarkerFaceColor', C(i, :)); %#ok<SAGROW>
    rho = spearman(V{i}, G{i});
    if mostrar_rho, txt{end + 1} = sprintf('%s (\\rho = %.2f)', nombres{i}, rho); %#ok<SAGROW>
    else, txt{end + 1} = nombres{i}; end %#ok<SAGROW>
end
if log_y, set(ax, 'YScale', 'log'); end
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if ~isempty(umbral), linea_referencia(ax, 'v', umbral, sprintf('umbral %.2f', umbral)); end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, txt, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
