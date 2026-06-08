// OptionHelpper.h: interface for the COptionHelpper class.
//
//////////////////////////////////////////////////////////////////////

#if !defined(AFX_OPTIONHELPPER_H__CBDB797D_51F4_445D_AF7B_6DFD23D35CB4__INCLUDED_)
#define AFX_OPTIONHELPPER_H__CBDB797D_51F4_445D_AF7B_6DFD23D35CB4__INCLUDED_

#if _MSC_VER > 1000
#pragma once
#endif // _MSC_VER > 1000

class COptionHelpper  
{
public:
	COptionHelpper();
	virtual ~COptionHelpper();

public:
    void SetCheckBaudTimes( int nTimes );
    void SetRepartitionFlag( int nFlag );
	void SetReadFlashBefRepFlag(int nFlag);
	BOOL SetProperty(LONG lFlags, _TCHAR* lpszName,LPCVOID pvarValue);
	BOOL GetProperty(LONG lFlags, _TCHAR* lpszName,LPVOID * pvarValue);

public:
    int  GetCheckBaudTimes( const _TCHAR* lpszFileType );
    int  GetTimeout( _TCHAR* lpszOperation );
    int  GetInterval( _TCHAR* lpszOperation );
    int  GetPacketLength( _TCHAR* lpszFileType );
    int  GetRepartitionFlag();
    BOOL GetFileOperations( _TCHAR* lpszFileType,CStringArray* pOperations );
    int  GetNVItemID();
	int  GetLogFlag();
	int  GetReadFlashBefRepFlag();
	int  Get7ENumOnce();
	UINT GetDefaultBaudrate();
	DWORD GetRomCodeBaudRate();
	BOOL IsEnablePortSecondEnum();
    BOOL IsEnablePowerOff();
    BOOL IsSupportZroPkg();
    BOOL IsNeedDoChkSum();
	BOOL SupportUnTransCode();
    BOOL IsNeedCheckOldMemory();
    BOOL IsGenCrcCfgFile();
    BOOL IsEnableCrcCfgCheck();
    CString GetCrcFile();

protected:
    int EnumKeys(_TCHAR* pSection,CStringArray* pKeys);

protected:
    int m_nCheckBaudTimes;
    int m_nRepartitionFlag;
	int m_nReadFlashBRFlag;
	CString m_strProduct;
	BOOL m_bChangeTimeOutSetting;
	BOOL m_bChangePacketLenSetting;
	BOOL m_bEnableSecondEnum;
    BOOL m_bPowerOff;
	DWORD m_dwRomCodeBaudrate;
};

#endif // !defined(AFX_OPTIONHELPPER_H__CBDB797D_51F4_445D_AF7B_6DFD23D35CB4__INCLUDED_)
