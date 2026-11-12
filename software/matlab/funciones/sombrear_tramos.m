function sombrear_tramos(ax, tramos_min, color, alfa)
% SOMBREAR_TRAMOS  Vertical bands over the [start end] intervals (in X-axis units).
    if nargin < 3 || isempty(color), color = [0.38 0.31 0.84]; end
    if nargin < 4, alfa = 0.12; end
    yl = ylim(ax);
    for j = 1:size(tramos_min, 1)
        a = tramos_min(j, 1);  b = tramos_min(j, 2);
        patch(ax, [a b b a], [yl(1) yl(1) yl(2) yl(2)], color, 'FaceAlpha', alfa, ...
              'EdgeColor', 'none', 'HandleVisibility', 'off');
    end
    ylim(ax, yl);
end
