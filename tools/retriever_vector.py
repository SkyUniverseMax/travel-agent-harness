import re
import numpy as np
import os
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings

# --- 全局变量：用于懒加载 ---
_retriever = None

# --- 路径部分 ---
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(current_file))
faq_path = os.path.join(project_root, 'order_faq.md')

def get_clean_docs():
    if not os.path.exists(faq_path):
        return []
    with open(faq_path, encoding='utf8') as f:
        faq_text = f.read()
    raw_texts = re.split(r"(?=\n##)", faq_text)
    clean_docs = []
    for txt in raw_texts:
        if txt:
            cleaned_str = str(txt).strip()
            if cleaned_str and len(cleaned_str) > 10:
                clean_docs.append({"page_content": cleaned_str})
    return clean_docs

def init_vector_store():
    global _retriever
    if _retriever is not None:
        return _retriever
    print(">>> 正在初始化阿里云向量检索器...")
    docs = get_clean_docs()
    if not docs:
        return None

    embeddings_model = OpenAIEmbeddings(
        model="text-embedding-v2",
        openai_api_key="xxxxxxxxxxxxxxx",
        openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        encoding_format="float",
        chunk_size=16
    )

    class VectorStoreRetriever:
        def __init__(self, docs, vectors):
            self._arr = np.array(vectors)
            self._docs = docs
        @classmethod
        def from_docs(cls, docs):
            input_list = [doc["page_content"] for doc in docs]
            print(f">>> 正在向量化 {len(input_list)} 个文档...")
            vectors = embeddings_model.embed_documents(input_list)
            return cls(docs, vectors)
        def query(self, query: str, k: int = 2):
            query_vec = embeddings_model.embed_query(str(query))
            scores = np.array(query_vec) @ self._arr.T
            top_k_idx = np.argpartition(scores, -k)[-k:]
            top_k_idx_sorted = top_k_idx[np.argsort(-scores[top_k_idx])]
            return [{**self._docs[idx], "similarity": float(scores[idx])} for idx in top_k_idx_sorted]

    try:
        _retriever = VectorStoreRetriever.from_docs(docs)
        print(">>> 初始化成功！")
        return _retriever
    except Exception as e:
        print(f">>> 初始化失败: {e}")
        return None

# --- 核心查询逻辑（普通函数，方便测试） ---
def _lookup_policy_logic(query: str) -> str:
    try:
        retriever = init_vector_store()
        if retriever:
            results = retriever.query(query)
            if results:
                context = "\n\n".join([r["page_content"] for r in results])
                return f"以下是查询到的相关政策：\n{context}"
        return "未找到相关政策。"
    except Exception as e:
        return f"查询出错: {str(e)}"

# --- LangChain 工具（给 Agent 用的） ---
@tool
def lookup_policy(query: str) -> str:
    """查询公司政策，检查某些选项是否允许。"""
    return _lookup_policy_logic(query)

# --- 测试部分 ---
if __name__ == '__main__':
    print("测试查询：怎么退票")
    # 注意：这里直接调用内部逻辑函数，而不是调用被 @tool 装饰过的对象
    print(_lookup_policy_logic("怎么退票"))