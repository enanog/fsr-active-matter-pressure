function [fig, ax] = nueva_figura(ancho_cm, alto_cm, fuente_pt, nombre)
% NUEVA_FIGURA  White figure of ANCHO_CM x ALTO_CM (true size in the PDF), font FUENTE_PT, light grid,
% no top/right box (report style). The window is named NOMBRE + the codes of the measurements just
% loaded, which are also stored on the figure (appdata 'codigos') for guardar_figura.
    if nargin < 1 || isempty(ancho_cm), ancho_cm = 17; end
    if nargin < 2 || isempty(alto_cm), alto_cm = 9; end
    if nargin < 3 || isempty(fuente_pt), fuente_pt = 10; end
    if nargin < 4, nombre = ''; end
    codigos = {};
    if isappdata(0, 'codigos_actuales'), codigos = getappdata(0, 'codigos_actuales'); end
    if ~isempty(codigos), nombre = sprintf('%s - %s', nombre, strjoin(codigos, ', ')); end
    fig = figure('Color', 'w', 'Units', 'centimeters', 'Position', [2 2 ancho_cm alto_cm], ...
                 'PaperUnits', 'centimeters', 'PaperSize', [ancho_cm alto_cm], ...
                 'PaperPosition', [0 0 ancho_cm alto_cm], 'Name', nombre, 'NumberTitle', 'off');
    setappdata(fig, 'codigos', codigos);
    ax = axes(fig);
    set(ax, 'FontSize', fuente_pt, 'Box', 'off', 'TickDir', 'out', 'LineWidth', 0.6, ...
            'XColor', [0.32 0.32 0.31], 'YColor', [0.32 0.32 0.31], ...
            'GridColor', [0.80 0.80 0.78], 'GridAlpha', 0.6, 'XGrid', 'on', 'YGrid', 'on');
    hold(ax, 'on');
end
