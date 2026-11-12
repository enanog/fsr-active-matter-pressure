function [x, y] = romper_huecos(t, y)
% ROMPER_HUECOS  Insert a NaN where time jumps (gap between the parts of a split recording) so the
% line is not drawn across it.
    x = t(:);  y = y(:);
    salto = find(diff(x) > 5 * median(diff(x)));
    for j = flipud(salto(:))'
        x = [x(1:j); (x(j) + x(j + 1)) / 2; x(j + 1:end)];
        y = [y(1:j); NaN; y(j + 1:end)];
    end
end
