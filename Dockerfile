FROM python:3.9
WORKDIR /calorily
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8080
ENV PYTHONUNBUFFERED "1"
CMD ["python", "-u", "-m", "calorily"]
