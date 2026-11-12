%% fig_giro_robots.m  -  giro propio de cada robot, ordenado (cuántos giran en cada sentido)
% One curve per trial: mean omega of each robot (or net turns), from the most clockwise to the most
% counter-clockwise. Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {'20260924_1600', '20261030_1200', '20261030_1600'};  % part of the code; 'todos'; {} = pick from a list
nombres  = {};             % legend texts in the same order; {} = automatic
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
que      = 'omega';        % 'omega' = mean omega of each robot [deg/s] | 'vueltas' = net turns over the trial
marcadores = true;
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = 'robots ordenados';
texto_y = '';              % '' = automatic
leyenda = 'northwest';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.2;
guardar = false;  archivo = 'giro_robots';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
marca = 'none';  if marcadores, marca = 'o'; end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'Giro por robot');
h = [];
for i = 1:numel(D)
    if strcmp(que, 'vueltas')
        th = D(i).TH;
        y = nan(1, D(i).N);
        for j = 1:D(i).N
            f = find(isfinite(th(:, j)));
            if ~isempty(f), y(j) = (th(f(end), j) - th(f(1), j)) / 360; end
        end
    else
        w = D(i).Wr;  ok = isfinite(w);  w(~ok) = 0;
        y = sum(w, 1) ./ sum(ok, 1);
    end
    y = sort(y);
    h(end + 1) = plot(ax, 1:numel(y), y, '-', 'Color', C(i, :), 'LineWidth', grosor, 'Marker', marca, ...
                      'MarkerSize', 4, 'MarkerFaceColor', C(i, :)); %#ok<SAGROW>
    corte = 0.5;  if strcmp(que, 'vueltas'), corte = 1; end      % same cut as comparar_modos.py
    fprintf('%s: %d antihorario, %d horario\n', D(i).etiqueta, nnz(y > corte), nnz(y < -corte));
end
plot(ax, xlim(ax), [0 0], 'Color', [0.45 0.45 0.43], 'LineWidth', 0.6, 'HandleVisibility', 'off');
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if isempty(texto_y)
    if strcmp(que, 'vueltas'), texto_y = 'vueltas netas (> 0 antihorario)'; else, texto_y = '\omega media [°/s] (> 0 antihorario)'; end
end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
