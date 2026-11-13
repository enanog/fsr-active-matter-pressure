%% fig_deltaG_distribucion.m  -  densidad de probabilidad de dG (varios ensayos o varias ventanas dT)
% Positive tail = pressure builds up, negative tail = it is released. Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {};   % {} = pick from a list of every trial (funciones/ensayos_base.m preselected) | 'todos' | {'...'} part of the code
deltaT_s = 2.5;            % one window [s] -> one curve per trial
                           % several windows, e.g. [0.5 2.5 10], with ONE trial -> one curve per window
nombres  = {};             % legend texts; {} = automatic
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
clases   = 80;
normalizar = true;         % X = dG / sigma(dG): compares the shape (tails) whatever the scale
recorte_sigma = 10;        % plotted range +-recorte_sigma standard deviations
log_y    = true;
gaussiana = true;          % reference normal curve (only with normalizar)
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = '';              % '' = automatic
texto_y = 'densidad de probabilidad';
leyenda = 'northeast';
ancho_cm = 17;  alto_cm = 9;  fuente = 10;  grosor = 1.3;
guardar = false;  archivo = 'deltaG_distribucion';  formatos = {'pdf', 'png'};
%% ==================================================================

R = cargar_presion(ensayos);
if numel(deltaT_s) > 1 && numel(R) > 1
    error('Varias ventanas dT solo con un ensayo (o un solo dT con varios ensayos).');
end
if numel(deltaT_s) > 1
    curvas = numel(deltaT_s);
    if iscell(colores) && isempty(colores)          % windows of one trial: palette in order
        colores = {'#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'};
    end
    C = colores_ensayos(repmat(R, 1, curvas), colores);
    auto = arrayfun(@(d) sprintf('\\DeltaT = %g s', d), deltaT_s, 'UniformOutput', false);
else
    curvas = numel(R);
    C = colores_ensayos(R, colores);
    auto = {R.etiqueta};
end
if isempty(nombres), nombres = auto; end
X = cell(1, curvas);
for k = 1:curvas
    if numel(deltaT_s) > 1, i = 1; dT = deltaT_s(k); else, i = k; dT = deltaT_s; end
    d = delta_g(R(i).P, dT);
    d = d(isfinite(d));
    if normalizar, d = (d - mean(d)) / std(d); end
    [a, ~] = momentos(d);
    fprintf('%s, dT = %g s: asimetría %.2f, %d muestras\n', R(i).etiqueta, dT, a, numel(d));
    X{k} = d;
end
if normalizar
    lim = recorte_sigma;
else
    lim = recorte_sigma * max(cellfun(@std, X));
end
bordes = linspace(-lim, lim, clases + 1);
centros = (bordes(1:end - 1) + bordes(2:end)) / 2;
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'Distribucion de Delta G');
h = [];
for k = 1:curvas
    n = histc(X{k}, bordes);
    n = [n(1:end - 2); n(end - 1) + n(end)]';
    p = n ./ (numel(X{k}) * diff(bordes));
    p(p == 0) = NaN;
    h(end + 1) = plot(ax, centros, p, 'Color', C(k, :), 'LineWidth', grosor); %#ok<SAGROW>
end
if gaussiana && normalizar
    h(end + 1) = plot(ax, centros, exp(-centros .^ 2 / 2) / sqrt(2 * pi), '--', ...
                      'Color', [0.45 0.45 0.43], 'LineWidth', 0.8);
    nombres{end + 1} = 'normal';
end
if log_y
    set(ax, 'YScale', 'log');
    y_datos = cell2mat(cellfun(@(c) get(c, 'YData'), num2cell(h(1:curvas)), 'UniformOutput', false));
    y_datos = y_datos(isfinite(y_datos) & y_datos > 0);
    ylim(ax, [min(y_datos) / 2, max(y_datos) * 2]);          % the normal curve does not set the range
end
if ~isempty(lim_x), xlim(ax, lim_x); else, xlim(ax, [-lim lim]); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if isempty(texto_x)
    if normalizar, texto_x = '\DeltaG / \sigma_{\DeltaG}'; else, texto_x = '\DeltaG [\muS]'; end
end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
