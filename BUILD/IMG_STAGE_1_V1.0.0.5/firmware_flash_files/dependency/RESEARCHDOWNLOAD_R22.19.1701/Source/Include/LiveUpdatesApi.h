#ifndef _LIVE_UPDATES_API_H_
#define _LIVE_UPDATES_API_H_

/// µ¼³öºê
#ifdef LIVEUPDATES_DLL_EXPORTS
#define LIVEUPDATES_API extern "C" __declspec(dllexport)
#else
#define LIVEUPDATES_API extern "C" __declspec(dllimport)
#endif

/** Check for version updates and automatically upgrade 
*
* @param bAuto          : Whether to automatically upgrade
* @param pszModuleName  : Absolute path of the application,such as "D:\Logel_R9.19.0402\Bin\ArmLogel.exe"
* @param pszPackageName : Such as Logel_R9.19.0402.rar --> "Logel"
* @param pExtend		: Reserved
*
* explanation :If using default parameters,the application file name must be same as the package name.
* e.g. CheckToolVerUpdate("D:\Logel_R9.19.0402\Bin\ArmLogel.exe", "Logel");
* e.g. CheckToolVerUpdate("D:\NVTOOL_R1.18.5101\Bin\NVTool.exe", "NVTool");
*/

LIVEUPDATES_API void CheckToolVerUpdate(BOOL bAuto = TRUE,
										const char* pszModuleName = NULL,
										const char* pszPackageName = NULL,
										void* pExtend = NULL);

#endif // _LIVE_UPDATES_API_H_
