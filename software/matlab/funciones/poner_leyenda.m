function lg = poner_leyenda(ax, h, textos, ubicacion)
% PONER_LEYENDA  Legend without a box; in MATLAB, clicking an entry hides / shows its curve.
%   ubicacion: 'best', 'northeast', 'northwest', 'southoutside', 'eastoutside', ... ; 'ninguna' = no legend
    if nargin < 4 || isempty(ubicacion), ubicacion = 'best'; end
    lg = [];
    if strcmpi(ubicacion, 'ninguna') || isempty(h), return; end
    lg = legend(ax, h, textos, 'Location', ubicacion, 'Box', 'off');
    try
        lg.ItemHitFcn = @alternar;          % not available in Octave: ignored
    catch
    end
end

function alternar(~, evento)
    obj = evento.Peer;
    if strcmp(obj.Visible, 'on'), obj.Visible = 'off'; else, obj.Visible = 'on'; end
end
