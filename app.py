import streamlit as st
from PyPDF2 import PdfReader
import pandas as pd
import base64
import os

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_anthropic import ChatAnthropic
from langchain.chains.question_answering import load_qa_chain
from langchain.prompts import PromptTemplate
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()


def get_pdf_text(pdf_docs):
    text = ""
    for pdf in pdf_docs:
        pdf_reader = PdfReader(pdf)
        for page in pdf_reader.pages:
            text += page.extract_text()
    return text


def get_text_chunks(text):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=10000,
        chunk_overlap=1000
    )
    return text_splitter.split_text(text)


def get_embeddings():
    return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")


def get_vector_store(text_chunks):
    embeddings = get_embeddings()
    vector_store = FAISS.from_texts(text_chunks, embedding=embeddings)
    vector_store.save_local("faiss_index")
    return vector_store


def get_conversational_chain(api_key):
    prompt_template = """
    Answer the question as detailed as possible from the provided context. Make sure to:

    1. Provide all relevant information with proper structure
    2. If the answer is not available in the provided context, clearly state that
    3. Do not provide incorrect information

    You are primarily analyzing documents (reports, contracts, research papers, etc.). Please:
    - Extract and summarize key information
    - Perform analysis based on the content
    - Identify important facts, figures, and conclusions
    - Be precise and cite specific sections when possible

    Context:\n{context}\n
    Question:\n{question}\n

    Answer:
    """
    model = ChatAnthropic(
        model="claude-sonnet-4-6",
        anthropic_api_key=api_key,
        temperature=0.3,
        max_tokens=4096,
    )
    prompt = PromptTemplate(
        template=prompt_template,
        input_variables=["context", "question"]
    )
    chain = load_qa_chain(model, chain_type="stuff", prompt=prompt)
    return chain


def user_input(user_question, api_key, pdf_docs, conversation_history):
    if not api_key or not pdf_docs:
        st.warning("Please upload PDF files and provide your Anthropic API key.")
        return

    with st.spinner("Thinking..."):
        text_chunks = get_text_chunks(get_pdf_text(pdf_docs))
        get_vector_store(text_chunks)

        embeddings = get_embeddings()
        db = FAISS.load_local("faiss_index", embeddings, allow_dangerous_deserialization=True)
        docs = db.similarity_search(user_question)

        chain = get_conversational_chain(api_key)
        response = chain(
            {"input_documents": docs, "question": user_question},
            return_only_outputs=True
        )

    response_text = response["output_text"]
    pdf_names = [pdf.name for pdf in pdf_docs]
    conversation_history.append((
        user_question,
        response_text,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ", ".join(pdf_names)
    ))

    st.markdown("""
    <style>
        .chat-message {
            padding: 1.5rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
            display: flex;
        }
        .chat-message.user { background-color: #2b313e; }
        .chat-message.bot  { background-color: #475063; }
        .chat-message .avatar { width: 20%; }
        .chat-message .avatar img {
            max-width: 78px;
            max-height: 78px;
            border-radius: 50%;
            object-fit: cover;
        }
        .chat-message .message {
            width: 80%;
            padding: 0 1.5rem;
            color: #fff;
        }
    </style>
    """, unsafe_allow_html=True)

    for q, a, ts, pdfs in reversed(conversation_history):
        st.markdown(f"""
        <div class="chat-message user">
            <div class="avatar">
                <img src="https://i.ibb.co/CKpTnWr/user-icon-2048x2048-ihoxz4vq.png">
            </div>
            <div class="message">{q}</div>
        </div>
        <div class="chat-message bot">
            <div class="avatar">
                <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Claude_AI_logo.svg/1024px-Claude_AI_logo.svg.png">
            </div>
            <div class="message">{a}</div>
        </div>
        """, unsafe_allow_html=True)

    if conversation_history:
        df = pd.DataFrame(
            conversation_history,
            columns=["Question", "Answer", "Timestamp", "PDF Name"]
        )
        csv = df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="conversation_history.csv"><button>Download conversation history as CSV</button></a>'
        st.sidebar.markdown(href, unsafe_allow_html=True)

    st.balloons()


def main():
    st.set_page_config(page_title="Chat with PDFs — Claude", page_icon=":books:")
    st.header("Chat with multiple PDFs using Claude :books:")

    if "conversation_history" not in st.session_state:
        st.session_state.conversation_history = []

    with st.sidebar:
        st.title("Settings")

        api_key = st.text_input(
            "Anthropic API Key",
            type="password",
            help="Get your key at https://console.anthropic.com"
        )
        if not api_key:
            st.warning("Enter your Anthropic API key to proceed.")

        st.markdown("---")

        pdf_docs = st.file_uploader(
            "Upload PDF files",
            accept_multiple_files=True,
            type=["pdf"]
        )

        col1, col2 = st.columns(2)
        if col1.button("Process"):
            if pdf_docs:
                with st.spinner("Processing PDFs..."):
                    try:
                        text = get_pdf_text(pdf_docs[:1])
                        if not text.strip():
                            st.warning("PDF appears empty or has no extractable text.")
                        else:
                            st.success("PDFs ready!")
                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.warning("Upload at least one PDF first.")

        if col2.button("Reset"):
            st.session_state.conversation_history = []
            st.rerun()

    user_question = st.text_input("Ask a question about your PDFs")
    if user_question:
        user_input(
            user_question,
            api_key,
            pdf_docs,
            st.session_state.conversation_history
        )


if __name__ == "__main__":
    main()
