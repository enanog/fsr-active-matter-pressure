%% fig_msd.m  -  desplazamiento cuadrático medio MSD(tau)
% Slope alpha (fit between 1 and 20 s): 1 = diffusive, 2 = ballistic. Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {};   % {} = pick from a list of every trial (funciones/ensayos_base.m preselected) | 'todos' | {'...'} part of the code
nombres  = {};             % legend texts; {} = automatic (adds alpha)
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
tau_max_s = [];            % largest lag [s]; [] = 1/4 of the trial (max 20 min)
referencias = true;        % dashed guide lines of slope 1 and 2
mostrar_alfa = true;
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = '\tau [s]';
texto_y = 'MSD [mm^2]';
leyenda = 'northwest';
ancho_cm = 12;  alto_cm = 9;  fuente = 10;  grosor = 1.4;
guardar = false;  archivo = 'msd';  formatos = {'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'MSD');
h = [];  txt = {};
for i = 1:numel(D)
    [tau, m, alfa] = desplazamiento_cuadratico(D(i), tau_max_s);
    h(end + 1) = plot(ax, tau, m, '-o', 'Color', C(i, :), 'LineWidth', grosor, 'MarkerSize', 3, ...
                      'MarkerFaceColor', C(i, :)); %#ok<SAGROW>
    if mostrar_alfa, txt{end + 1} = sprintf('%s (\\alpha = %.2f)', nombres{i}, alfa); %#ok<SAGROW>
    else, txt{end + 1} = nombres{i}; end %#ok<SAGROW>
end
set(ax, 'XScale', 'log', 'YScale', 'log');
if referencias
    xl = xlim(ax);  yl = ylim(ax);
    x0 = xl(1);  y0 = yl(1) * 3;
    for s = [1 2]
        x1 = min(xl(2), x0 * (yl(2) / y0) ^ (1 / s));
        plot(ax, [x0 x1], y0 * [1 (x1 / x0) ^ s], '--', 'Color', [0.6 0.6 0.58], 'LineWidth', 0.7, 'HandleVisibility', 'off');
        text(ax, x1, y0 * (x1 / x0) ^ s, sprintf(' pendiente %d', s), 'FontSize', fuente - 2, 'Color', [0.45 0.45 0.43]);
    end
    xlim(ax, xl);  ylim(ax, yl);
end
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, txt, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
