import uvicorn
import sys
import config


if __name__ == "__main__":
    if not config.DEBUG:
        print("Warning: trying to launch using debug feature on a non-debug settings. This is not allowed. Please turn on DEBUG or use a real launch tool.", file=sys.stderr)
        exit(1)
    uvicorn.run("application:app", host=config.RUN_ADDR, port=config.RUN_PORT, reload=True)