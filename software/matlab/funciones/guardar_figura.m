function guardar_figura(fig, archivo, formatos)
% GUARDAR_FIGURA  Save FIG as informes/figuras/matlab/<archivo>.<format> (or at ARCHIVO if it includes a
% folder). formatos: {'pdf', 'png'} by default; also 'svg', 'eps', 'fig'.
% The codes of the measurements in the figure are appended to the name (see nombre_con_codigos), so
% figures of different trials never overwrite each other: velocidad_tiempo__20261030_1100_22AH_60-...
    if nargin < 3 || isempty(formatos), formatos = {'pdf', 'png'}; end
    if ischar(formatos), formatos = {formatos}; end
    [carpeta, nombre] = fileparts(archivo);
    if isappdata(fig, 'codigos'), nombre = nombre_con_codigos(nombre, getappdata(fig, 'codigos')); end
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
