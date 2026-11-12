function linea_referencia(ax, orientacion, valor, texto, color)
% LINEA_REFERENCIA  Dashed horizontal ('h') or vertical ('v') line with a label (e.g. the threshold).
    if nargin < 4, texto = ''; end
    if nargin < 5 || isempty(color), color = [0.45 0.45 0.43]; end
    xl = xlim(ax);  yl = ylim(ax);
    if orientacion == 'h'
        plot(ax, xl, [valor valor], '--', 'Color', color, 'LineWidth', 0.8, 'HandleVisibility', 'off');
        if ~isempty(texto), text(ax, xl(2), valor, [texto ' '], 'HorizontalAlignment', 'right', ...
                'VerticalAlignment', 'bottom', 'Color', color, 'FontSize', get(ax, 'FontSize') - 1); end
    else
        plot(ax, [valor valor], yl, '--', 'Color', color, 'LineWidth', 0.8, 'HandleVisibility', 'off');
        if ~isempty(texto), text(ax, valor, yl(2), [' ' texto], 'VerticalAlignment', 'top', ...
                'Color', color, 'FontSize', get(ax, 'FontSize') - 1); end
    end
    xlim(ax, xl);  ylim(ax, yl);
end
