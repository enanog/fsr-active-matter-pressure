%% fig_ocupacion.m  -  mapa de ocupación del recinto, un panel por ensayo
% Mean number of robot centres per cm^2, seen by the observer (y away from them). Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {};   % {} = pick from a list of every trial (funciones/ensayos_base.m preselected) | 'todos' | {'...'} part of the code
nombres  = {};             % panel titles; {} = automatic
celda_mm = 5;              % cell size [mm]
subconjunto = 'todo';      % 'todo' | 'atasco' | 'fluido'
umbral   = 0.35;           % jam threshold [mm/s] (for 'atasco' / 'fluido')
escala_log = false;        % logarithmic colour scale
mapa     = 'parula';       % colormap: 'parula', 'hot', 'gray', 'turbo', ...
misma_escala = true;       % same colour range in every panel
tope_percentil = 99;       % colour range up to this percentile of the cells (robots stuck in a jam saturate)
circulo_pared = true;      % inner wall (diameter 185 mm)
columnas = [];             % panels per row; [] = all in one row
ancho_cm = 17;  alto_cm = 6.5;  fuente = 9;
guardar = false;  archivo = 'ocupacion';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
if isempty(nombres), nombres = {D.etiqueta}; end
n = numel(D);
if isempty(columnas), columnas = n; end
filas_pan = ceil(n / columnas);
[fig, ax0] = nueva_figura(ancho_cm, alto_cm * filas_pan, fuente, 'Ocupacion');
delete(ax0);
R_int = 92.5;
b = -R_int:celda_mm:R_int;
mapas = cell(1, n);
for i = 1:n
    X = D(i).X;  Y = D(i).Y;
    if ~strcmp(subconjunto, 'todo')
        A = atascos(D(i), umbral);
        f = A.mascara;  if strcmp(subconjunto, 'fluido'), f = ~f; end
        X = X(f, :);  Y = Y(f, :);
    end
    ok = isfinite(X) & isfinite(Y);
    ix = floor((X(ok) - b(1)) / celda_mm) + 1;  iy = floor((Y(ok) - b(1)) / celda_mm) + 1;
    dentro = ix >= 1 & iy >= 1 & ix < numel(b) & iy < numel(b);
    H = accumarray([iy(dentro), ix(dentro)], 1, [numel(b) - 1, numel(b) - 1]);
    H = H / size(X, 1) / (celda_mm / 10) ^ 2;            % robots per cm^2, averaged over frames
    if escala_log, H(H == 0) = NaN; H = log10(H); end
    mapas{i} = H;
end
todos = cell2mat(cellfun(@(m) m(:), mapas, 'UniformOutput', false)');
rango = [min(todos(isfinite(todos))), percentil(todos(isfinite(todos) & todos > 0), tope_percentil)];
c = (b(1:end - 1) + b(2:end)) / 2 / 10;                  % cm
for i = 1:n
    ax = subplot(filas_pan, columnas, i);
    imagesc(ax, c, c, mapas{i});
    set(ax, 'YDir', 'normal', 'FontSize', fuente, 'Box', 'off', 'TickDir', 'out');
    axis(ax, 'equal');  axis(ax, 'tight');
    try
        colormap(ax, mapa);
    catch
        colormap(ax, 'viridis');                 % Octave has no parula
    end
    if misma_escala, caxis(ax, rango); end
    hold(ax, 'on');
    if circulo_pared
        a = linspace(0, 2 * pi, 200);
        plot(ax, R_int / 10 * cos(a), R_int / 10 * sin(a), 'Color', [0.9 0.9 0.9], 'LineWidth', 0.8);
    end
    title(ax, texto_tex(nombres{i}));
    xlabel(ax, 'x [cm]');
    if mod(i - 1, columnas) == 0, ylabel(ax, 'y [cm]'); end
    if ~misma_escala || i == n
        cb = colorbar(ax);
        if escala_log, ylabel(cb, 'log_{10} robots/cm^2'); else, ylabel(cb, 'robots/cm^2'); end
    end
end
if guardar, guardar_figura(fig, archivo, formatos); end
