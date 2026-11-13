%% fig_hexbin_velocidad_presion.m  -  V media en función de G: densidad por celdas (histogram2 o hexbin)
% Every video frame is one point: x = G of the sensor at that instant (inside the FSRScope mask), y = V media
% of the group (or |v| of every observed robot). Rectangles: MATLAB's histogram2. Hexagons: MATLAB has no
% built-in hexbin, so funciones/hexbin.m bins and patch draws. Same cells and colour scale in every panel.
% Requires MATLAB R2020b or later (tiledlayout with a shared colorbar). Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {};             % {} = pick from a list of every trial (funciones/ensayos_base.m preselected) | 'todos' | {'...'} part of the code
nombres  = {};             % panel titles; {} = measurement code
tipo     = 'histogram2';   % 'histogram2' (rectangles) | 'hexbin' (hexagons)
fuente_v = 'media';        % 'media' = V of the group per frame | 'individual' = |v| of every observed robot
suavizado_s = 0;           % moving average of V and G [s] (only 'media'); 0 = raw frames
celdas   = [40 30];        % cells along G and along V (hexbin: only the first; rows follow for regular hexagons)
G_log    = true;           % logarithmic G axis (cells regular in log10 G)
G_minimo = 1e-3;           % G below this is left out with G_log [uS]
lim_G = [];  lim_V = [];   % axis ranges, e.g. [1e-2 1e3] and [0 2]; [] = from the data (same in every panel)
normalizacion = 'probability';   % 'probability' (fraction of the trial's points) | 'count' (frames)
color_log = true;          % logarithmic colour scale
mapa     = 'parula';
juntar   = false;          % true: every trial in one panel
mostrar_rho = true;        % Spearman rho(G, V) under each title
umbral   = 0.35;           % horizontal line at the jam threshold [mm/s]; [] = none
columnas = [];             % panels per row; [] = up to 3
texto_x = 'G [\muS]';
texto_y = '';              % '' = automatic
ancho_cm = 17;  alto_cm = 7;  fuente = 9;     % alto_cm = height of each row of panels
guardar = false;  archivo = '';  formatos = {'pdf', 'png'};   % '' = 'hist2_velocidad_presion' or 'hexbin_velocidad_presion'
%% ==================================================================

D = cargar_ensayos(ensayos);
if isempty(nombres), nombres = {D.etiqueta}; end
X = cell(1, numel(D));  Y = X;
for i = 1:numel(D)
    g = presion_en_cuadros(D(i), suavizado_s);
    if strcmp(fuente_v, 'individual')
        v = D(i).S;  v(~D(i).OBS) = NaN;
        g = repmat(g, 1, size(v, 2));
    elseif suavizado_s > 0
        v = movmean(D(i).V, suavizado_s, 'omitnan', 'SamplePoints', D(i).t);
    else
        v = D(i).V;
    end
    ok = isfinite(g) & isfinite(v) & (~G_log | g >= G_minimo);
    X{i} = g(ok);  Y{i} = v(ok);
end
hay = ~cellfun(@isempty, X);
if ~any(hay), error('Ningún ensayo tiene G y V a la vez.'); end
if ~all(hay), fprintf('Sin registro de G, quedan afuera: %s\n', strjoin({D(~hay).codigo}, ', ')); end
X = X(hay);  Y = Y(hay);  nombres = nombres(hay);
if juntar
    X = {vertcat(X{:})};  Y = {vertcat(Y{:})};  nombres = {sprintf('%d ensayos juntos', nnz(hay))};
end
rho = cellfun(@spearman, X, Y);           % corr(..., 'Type', 'Spearman') needs the Statistics Toolbox

% --- common cells for every panel
todos_x = vertcat(X{:});  todos_y = vertcat(Y{:});
if isempty(lim_G), lim_G = [min(todos_x) max(todos_x)]; end
if isempty(lim_V), lim_V = [min(0, min(todos_y)) max(todos_y)]; end
if G_log
    xe = logspace(log10(lim_G(1)), log10(lim_G(2)), celdas(1) + 1);
else
    xe = linspace(lim_G(1), lim_G(2), celdas(1) + 1);
end
ye = linspace(lim_V(1), lim_V(2), celdas(2) + 1);

% --- panels
n = numel(X);
if isempty(columnas), columnas = min(n, 3); end
filas = ceil(n / columnas);
if strcmp(tipo, 'hexbin'), titulo_fig = 'Hexbin V vs G'; else, titulo_fig = 'Histograma 2D V vs G'; end
[fig, ax0] = nueva_figura(ancho_cm, alto_cm * filas, fuente, titulo_fig);
delete(ax0);
t = tiledlayout(fig, filas, columnas, 'TileSpacing', 'compact', 'Padding', 'compact');
ejes = gobjects(1, n);  valores = cell(1, n);
for i = 1:n
    ax = nexttile(t);  ejes(i) = ax;
    switch tipo
        case 'histogram2'
            h = histogram2(ax, X{i}, Y{i}, xe, ye, 'DisplayStyle', 'tile', 'ShowEmptyBins', 'off', ...
                           'Normalization', normalizacion, 'EdgeColor', 'none');
            valores{i} = h.Values(h.Values > 0);
        case 'hexbin'
            u = X{i};  lx = xe([1 end]);
            if G_log, u = log10(u); lx = log10(lx); end
            filas_hex = max(1, round(celdas(1) * (alto_cm / (ancho_cm / columnas)) / sqrt(3)));
            H = hexbin(u, Y{i}, celdas(1), filas_hex, lx, ye([1 end]));
            c = H.n;
            if strcmp(normalizacion, 'probability'), c = c / numel(u); end
            vx = (H.cx + H.dx)';  vy = (H.cy + H.dy)';          % 6 x hexagons
            if G_log, vx = 10 .^ vx; end
            patch(ax, vx, vy, c', 'EdgeColor', 'none');
            valores{i} = c;
        otherwise
            error('tipo = histogram2 | hexbin');
    end
    if G_log, ax.XScale = 'log'; end
    xlim(ax, xe([1 end]));  ylim(ax, ye([1 end]));
    colormap(ax, mapa);
    if color_log, ax.ColorScale = 'log'; end
    if ~isempty(umbral), yline(ax, umbral, '--', sprintf('umbral %.2f', umbral), 'Color', [0.45 0.45 0.43]); end
    titulo = nombres{i};
    if mostrar_rho, titulo = {titulo, sprintf('ρ = %.2f', rho(i))}; end
    title(ax, titulo, 'Interpreter', 'none');
    set(ax, 'FontSize', fuente, 'Box', 'off', 'TickDir', 'out', 'Layer', 'top');
    grid(ax, 'on');
end
v = vertcat(valores{:});
set(ejes, 'CLim', [min(v) max(v)]);                 % one colour scale for every panel

cb = colorbar(ejes(end));
cb.Layout.Tile = 'east';                            % one colorbar for the whole layout
if strcmp(fuente_v, 'individual'), unidad = 'robot·cuadros'; else, unidad = 'cuadros'; end
if strcmp(normalizacion, 'probability'), cb.Label.String = ['fracción de los ' unidad]; else, cb.Label.String = unidad; end
if isempty(texto_y)
    if strcmp(fuente_v, 'individual'), texto_y = '|v| [mm/s]'; else, texto_y = 'V_{media} [mm/s]'; end
end
xlabel(t, texto_x, 'FontSize', fuente);  ylabel(t, texto_y, 'FontSize', fuente);
if isempty(archivo)
    if strcmp(tipo, 'hexbin'), archivo = 'hexbin_velocidad_presion'; else, archivo = 'hist2_velocidad_presion'; end
end
if guardar, guardar_figura(fig, archivo, formatos); end
