/**
 * Minimal CSInterface for CEP panels (Adobe Common Extensibility Platform).
 * Based on Adobe CEP 9 samples.
 */
(function () {
  function CSInterface() {}

  CSInterface.prototype.getSystemPath = function (pathType) {
    var path = decodeURI(window.__adobe_cep__.getSystemPath(pathType));
    return path;
  };

  CSInterface.prototype.evalScript = function (script, callback) {
    if (callback === null || callback === undefined) {
      callback = function () {};
    }
    window.__adobe_cep__.evalScript(script, callback);
  };

  CSInterface.prototype.getHostEnvironment = function () {
    var hostEnv = window.__adobe_cep__.getHostEnvironment();
    return JSON.parse(hostEnv);
  };

  window.CSInterface = CSInterface;
  window.SystemPath = {
    USER_DATA: "userData",
    COMMON_FILES: "commonFiles",
    MY_DOCUMENTS: "myDocuments",
    APPLICATION: "application",
    EXTENSION: "extension",
    HOST_APPLICATION: "hostApplication",
  };
})();
