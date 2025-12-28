import os




import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold


class gemini_api:
    def __init__(self, api_key=None, system_prompt: str = None, tools=None):
        # API 키 설정 (인자로 받거나 기본값 사용)
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = "[INPUT your gemini api key]"
        
        genai.configure(api_key=self.api_key)

        # 모델 설정
        model_config = {
            "model_name": "gemini-2.5-flash-lite"
        }
        
        self.model = genai.GenerativeModel(**model_config)
        
        # System prompt 저장 (나중에 프롬프트에 포함)
        self.system_prompt = system_prompt
        
        # Tools 저장 (Function calling은 나중에 generate_content에서 처리)
        self.tools = tools

    def request(self, input_text: str):
        """기본 요청 메서드"""
        # System prompt가 있으면 프롬프트 앞에 추가
        if self.system_prompt:
            full_prompt = f"{self.system_prompt}\n\n{input_text}"
        else:
            full_prompt = input_text
        
        response = self.model.generate_content(full_prompt)
        return response.text
    
    def get_response(self, input_text: str):
        """응답 객체 전체 반환 (Function calling 지원)"""
        # System prompt가 있으면 프롬프트 앞에 추가
        if self.system_prompt:
            full_prompt = f"{self.system_prompt}\n\n{input_text}"
        else:
            full_prompt = input_text
        
        # Tools가 있으면 generate_content에 전달
        if self.tools:
            # 라이브러리 버전 확인
            import google.generativeai as genai
            version = genai.__version__
            print(f"📦 google-generativeai 버전: {version}")
            
            # 버전 파싱
            try:
                version_parts = [int(x) for x in version.split('.')]
                major, minor = version_parts[0], version_parts[1]
            except:
                major, minor = 0, 0
            
            # 0.3.x 버전은 Function Calling 미지원
            if major == 0 and minor < 4:
                error_msg = f"버전 {version}은 Function Calling을 지원하지 않습니다. 0.4.0 이상으로 업그레이드하세요."
                print(f"❌ {error_msg}")
                raise ImportError(error_msg)
            
            # 버전에 따라 다른 방법 시도
            FunctionDeclaration = None
            Tool = None
            
            # 방법 1: 최신 버전 (0.8.6 이상 또는 types에서 직접 import 가능한 경우)
            try:
                from google.generativeai.types import FunctionDeclaration, Tool
                print("✅ 방법 1 성공: types에서 직접 import")
            except ImportError:
                # 방법 2: 0.8.x 버전 - content_types에서 직접 접근
                try:
                    import google.generativeai.types.content_types as content_types
                    
                    # 속성 확인
                    if hasattr(content_types, 'FunctionDeclaration'):
                        FunctionDeclaration = content_types.FunctionDeclaration
                    if hasattr(content_types, 'Tool'):
                        Tool = content_types.Tool
                    
                    if FunctionDeclaration and Tool:
                        print("✅ 방법 2 성공: content_types에서 직접 접근")
                    else:
                        raise AttributeError("FunctionDeclaration 또는 Tool 속성을 찾을 수 없음")
                except Exception as e:
                    print(f"⚠️  방법 2 실패: {e}")
                    # 방법 3: getattr로 시도
                    try:
                        import google.generativeai.types.content_types as content_types
                        FunctionDeclaration = getattr(content_types, 'FunctionDeclaration', None)
                        Tool = getattr(content_types, 'Tool', None)
                        if FunctionDeclaration and Tool:
                            print("✅ 방법 3 성공: getattr 사용")
                    except Exception as e3:
                        print(f"⚠️  방법 3 실패: {e3}")
            
            if FunctionDeclaration is None or Tool is None:
                error_msg = f"FunctionDeclaration/Tool import 실패 (버전: {version}). 버전 0.4.0 이상이 필요합니다."
                print(f"❌ {error_msg}")
                raise ImportError(error_msg)
            
            try:
                # 함수 정의를 FunctionDeclaration 객체로 변환
                function_declarations = []
                for tool in self.tools:
                    func_decl = FunctionDeclaration(
                        name=tool["name"],
                        description=tool.get("description", ""),
                        parameters={
                            "type": "object",
                            "properties": tool["parameters"]["properties"],
                            "required": tool["parameters"].get("required", [])
                        }
                    )
                    function_declarations.append(func_decl)
                
                # Tool 객체 생성
                tool_obj = Tool(function_declarations=function_declarations)
                
                # generate_content에 tools 전달
                response = self.model.generate_content(
                    full_prompt,
                    tools=[tool_obj]
                )
                print("✅ Function Calling 활성화됨")
            except Exception as e:
                error_msg = f"Function calling 변환 실패: {e}"
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()
                raise RuntimeError(error_msg) from e
        else:
            response = self.model.generate_content(full_prompt)
        
        return response