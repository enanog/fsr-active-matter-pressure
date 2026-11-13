%% fig_densidad_radial.m  -  densidad de robots en función de la distancia al centro (capas)
% Density of robot centres per ring, relative to a uniform distribution (1 = uniform), vs r / Rc
% (Rc = radius of the centres touching the wall). Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = {};   % {} = pick from a list of every trial (funciones/ensayos_base.m preselected) | 'todos' | {'...'} part of the code
nombres  = {};             % legend texts in the same order; {} = automatic
colores  = {};             % {} = project palette | 'modo' | {'#2a78d6', ...}
eje_mm   = false;          % X in mm instead of r / Rc
clases   = 25;
subconjunto = 'todo';      % 'todo' | 'atasco' | 'fluido' (frames inside / outside jams)
umbral   = 0.35;           % jam threshold [mm/s] (for 'atasco' / 'fluido')
marcar_pared = true;       % line at the start of the wall layer (Rc - D/2)
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = '';              % '' = automatic
texto_y = 'densidad relativa';
leyenda = 'northwest';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.4;
guardar = false;  archivo = 'densidad_radial';  formatos = {'pdf', 'png'};
%% ==================================================================

D = cargar_ensayos(ensayos);
C = colores_ensayos(D, colores);
if isempty(nombres), nombres = {D.etiqueta}; end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'Densidad radial');
h = [];  Rcs = zeros(1, numel(D));
for i = 1:numel(D)
    r = hypot(D(i).X, D(i).Y);
    Rc = radio_contacto(D(i));  Rcs(i) = Rc;
    if ~strcmp(subconjunto, 'todo')
        A = atascos(D(i), umbral);
        filas = A.mascara;
        if strcmp(subconjunto, 'fluido'), filas = ~filas; end
        r = r(filas, :);
    end
    u = r(isfinite(r)) / Rc;
    u = min(u, 1 - 1e-9);
    bordes = linspace(0, 1, clases + 1);
    n = histc(u, bordes);  n = n(1:end - 1)';
    area = pi * (bordes(2:end) .^ 2 - bordes(1:end - 1) .^ 2);
    dens = n ./ area / (sum(n) / pi);                % 1 = uniform over the disc of radius Rc
    x = (bordes(1:end - 1) + bordes(2:end)) / 2;
    if eje_mm, x = x * Rc; end
    h(end + 1) = plot(ax, x, dens, '-o', 'Color', C(i, :), 'LineWidth', grosor, 'MarkerSize', 3, ...
                      'MarkerFaceColor', C(i, :)); %#ok<SAGROW>
end
if marcar_pared
    xp = 1 - 33 / 2 / mean(Rcs);  if eje_mm, xp = mean(Rcs) - 33 / 2; end
    linea_referencia(ax, 'v', xp, 'capa de pared');
end
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if isempty(texto_x)
    if eje_mm, texto_x = 'r [mm]'; else, texto_x = 'r / R_c'; end
end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
