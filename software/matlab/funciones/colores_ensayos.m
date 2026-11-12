function C = colores_ensayos(D, colores)
% COLORES_ENSAYOS  One RGB colour (row) per trial in D.
%   colores = {}            -> project palette; a trial keeps its colour in every figure, whatever
%                              else is selected (8 colours: past 8 trials they repeat -> use 'modo' or a list)
%   colores = 'modo'        -> by mode: AH (counter-clockwise) blue, HO (clockwise) orange, AL (random) aqua
%   colores = {'#2a78d6', [0.9 0.4 0.2], 'k', ...}  -> any colours, in the order of the trials
    paleta = {'#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'};
    por_modo = struct('AH', '#2a78d6', 'HO', '#eb6834', 'AL', '#1baf7a');
    if nargin < 2, colores = {}; end
    C = zeros(numel(D), 3);
    todos = unique([buscar_registros(), buscar_ensayos()]);   % same index in every figure
    for i = 1:numel(D)
        if ischar(colores) && strcmpi(colores, 'modo')
            c = '#52514e';
            if isfield(por_modo, D(i).modo), c = por_modo.(D(i).modo); end
        elseif iscell(colores) && numel(colores) >= i && ~isempty(colores{i})
            c = colores{i};
        else
            j = find(strcmp(todos, D(i).codigo), 1);
            if isempty(j), j = i; end
            c = paleta{mod(j - 1, numel(paleta)) + 1};
        end
        C(i, :) = a_rgb(c);
    end
end

function rgb = a_rgb(c)
    if isnumeric(c), rgb = c(:)'; return; end
    if c(1) == '#'
        rgb = [hex2dec(c(2:3)), hex2dec(c(4:5)), hex2dec(c(6:7))] / 255;
        return
    end
    nombres = struct('k', [0 0 0], 'r', [1 0 0], 'g', [0 0.6 0], 'b', [0 0 1], 'm', [1 0 1], ...
                     'c', [0 0.75 0.75], 'y', [0.9 0.75 0], 'w', [1 1 1]);
    rgb = nombres.(c);
end
