function r = raiz_proyecto()
% RAIZ_PROYECTO  Repository folder (the one holding datos/), from the location of this file:
% software/matlab/funciones/raiz_proyecto.m -> three levels up. Works wherever the repo is.
    r = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
    if ~isfolder(fullfile(r, 'datos'))
        error('No encuentro datos/ en %s. ¿Se movió la carpeta software/matlab?', r);
    end
end
