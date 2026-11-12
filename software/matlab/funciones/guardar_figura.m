function guardar_figura(fig, archivo, formatos)
% GUARDAR_FIGURA  Save FIG as informes/figuras/matlab/<archivo>.<format> (or at ARCHIVO if it includes a
% folder). formatos: {'pdf', 'png'} by default; also 'svg', 'eps', 'fig'.
    if nargin < 3 || isempty(formatos), formatos = {'pdf', 'png'}; end
    if ischar(formatos), formatos = {formatos}; end
    [carpeta, nombre] = fileparts(archivo);
    if isempty(carpeta), carpeta = fullfile(raiz_proyecto(), 'informes', 'figuras', 'matlab'); end
    if ~isfolder(carpeta), mkdir(carpeta); end
    for k = 1:numel(formatos)
        f = fullfile(carpeta, [nombre '.' formatos{k}]);
        switch lower(formatos{k})
            case 'fig'
                savefig(fig, f);
            case 'pdf'
                if exist('exportgraphics', 'file')
                    exportgraphics(fig, f, 'ContentType', 'vector');
                else
                    print(fig, f, '-dpdf');
                end
            case 'png'
                if exist('exportgraphics', 'file')
                    exportgraphics(fig, f, 'Resolution', 300);
                else
                    print(fig, f, '-dpng', '-r300');
                end
            otherwise
                print(fig, f, ['-d' lower(formatos{k})]);
        end
        fprintf('Guardada: %s\n', f);
    end
end
