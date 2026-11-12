%% fig_presion_tiempo.m  -  conductancia del sensor G vs tiempo (una curva por ensayo)
% Any sensor log (also the ones without video). Uses the FSRScope calibration, crop, exclusions and
% sync of each trial. Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos     = {'20260924_1600', '20261030_1200', '20261030_1600'};  % part of the code; 'todos'; {} = pick from a list
nombres     = {};          % legend texts in the same order; {} = automatic
colores     = {};          % {} = project palette | 'modo' | {'#2a78d6', ...}
eje_tiempo  = 'video';     % 'video' = minutes of video (same axis as the speed plots; t = t_sensor - desfase)
                           % 'sensor' = minutes from the start of the log
suavizado_s = 30;          % moving average [s]; 0 = raw (20 Hz)
solo_mascara = true;       % hide what FSRScope crops / excludes
marcar_saturacion = false; % grey band where the ADC saturates (G is only a lower bound there)
escala_log  = true;        % logarithmic Y axis (G spans several decades)
G_minimo    = 1e-3;        % values below are hidden in log scale [uS]
lim_x = [];  lim_y = [];
titulo  = '';
texto_x = 't [min]';
texto_y = 'G [\muS]';
leyenda = 'northwest';
ancho_cm = 17;  alto_cm = 8;  fuente = 10;  grosor = 1.0;
guardar = false;  archivo = 'presion_tiempo';  formatos = {'pdf', 'png'};
%% ==================================================================

R = cargar_presion(ensayos);
C = colores_ensayos(R, colores);
if isempty(nombres), nombres = {R.etiqueta}; end
[fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente, 'Presion vs tiempo');
h = [];
for i = 1:numel(R)
    P = R(i).P;
    t = P.t;
    if strcmp(eje_tiempo, 'video'), t = t - P.offset; end
    G = P.G;
    if solo_mascara, G = presion_valida(P); end
    G = suavizar(P.t, G, suavizado_s);
    if solo_mascara, G(~P.mascara) = NaN; end
    if escala_log, G(G < G_minimo) = NaN; end
    if strcmp(eje_tiempo, 'video'), G(t < 0) = NaN; end
    h(end + 1) = plot(ax, t / 60, G, 'Color', C(i, :), 'LineWidth', grosor); %#ok<SAGROW>
end
if escala_log, set(ax, 'YScale', 'log'); end
if strcmp(eje_tiempo, 'video'), xlim(ax, [0, max(xlim(ax))]); end
if ~isempty(lim_x), xlim(ax, lim_x); end
if ~isempty(lim_y), ylim(ax, lim_y); end
if marcar_saturacion
    for i = 1:numel(R)
        s = R(i).P.sat;  t = R(i).P.t;
        if strcmp(eje_tiempo, 'video'), t = t - R(i).P.offset; end
        d = diff([false; s; false]);
        sombrear_tramos(ax, [t(d(1:end - 1) == 1), t(d(2:end) == -1)] / 60, [0.5 0.5 0.5], 0.15);
    end
end
xlabel(ax, texto_x);  ylabel(ax, texto_y);  title(ax, titulo);
poner_leyenda(ax, h, nombres, leyenda);
if guardar, guardar_figura(fig, archivo, formatos); end
