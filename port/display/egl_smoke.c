/* SPDX-License-Identifier: Apache-2.0
 * Exercise the supplied HMOS Mesa stack without exposing host graphics.
 */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <dlfcn.h>
#include <stdio.h>

#define LOAD(handle, name) __typeof__(&name) p_##name = dlsym(handle, #name); \
    if (!p_##name) { fprintf(stderr, "missing %s\n", #name); return 1; }
#define CHECK(test) do { if (!(test)) { \
    fprintf(stderr, "FAIL %s EGL error=0x%x\n", #test, p_eglGetError()); return 1; } } while (0)

int main(void)
{
    void *egl = dlopen("/vendor/lib64/libEGL_impl.so", RTLD_NOW | RTLD_GLOBAL);
    if (!egl) { fprintf(stderr, "EGL load failed: %s\n", dlerror()); return 1; }
    void *gles = dlopen("/vendor/lib64/libGLESv2_impl.so", RTLD_NOW | RTLD_LOCAL);
    if (!gles) { fprintf(stderr, "GLES load failed: %s\n", dlerror()); return 1; }
    LOAD(egl, eglGetError); LOAD(egl, eglGetProcAddress); LOAD(egl, eglInitialize);
    LOAD(egl, eglChooseConfig); LOAD(egl, eglBindAPI); LOAD(egl, eglCreateContext);
    LOAD(egl, eglCreatePbufferSurface); LOAD(egl, eglMakeCurrent);
    LOAD(egl, eglDestroySurface); LOAD(egl, eglDestroyContext); LOAD(egl, eglTerminate);
    LOAD(gles, glGetString); LOAD(gles, glClearColor); LOAD(gles, glClear);
    LOAD(gles, glReadPixels); LOAD(gles, glGetError);
    LOAD(gles, glCreateShader); LOAD(gles, glShaderSource); LOAD(gles, glCompileShader);
    LOAD(gles, glGetShaderiv); LOAD(gles, glCreateProgram); LOAD(gles, glAttachShader);
    LOAD(gles, glBindAttribLocation); LOAD(gles, glLinkProgram); LOAD(gles, glGetProgramiv);
    LOAD(gles, glUseProgram); LOAD(gles, glVertexAttribPointer); LOAD(gles, glEnableVertexAttribArray);
    LOAD(gles, glViewport); LOAD(gles, glDrawArrays); LOAD(gles, glDeleteShader);
    LOAD(gles, glDeleteProgram);
    PFNEGLGETPLATFORMDISPLAYEXTPROC platform =
        (PFNEGLGETPLATFORMDISPLAYEXTPROC)p_eglGetProcAddress("eglGetPlatformDisplayEXT");
    CHECK(platform);
    EGLDisplay display = platform(EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, NULL);
    CHECK(display != EGL_NO_DISPLAY);
    EGLint major, minor;
    CHECK(p_eglInitialize(display, &major, &minor));
    const EGLint attributes[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_RED_SIZE, 8,
        EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
    EGLConfig config; EGLint count;
    CHECK(p_eglChooseConfig(display, attributes, &config, 1, &count) && count == 1);
    CHECK(p_eglBindAPI(EGL_OPENGL_ES_API));
    const EGLint context_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    EGLContext context = p_eglCreateContext(display, config, EGL_NO_CONTEXT, context_attributes);
    CHECK(context != EGL_NO_CONTEXT);
    const EGLint surface_attributes[] = {EGL_WIDTH, 4, EGL_HEIGHT, 4, EGL_NONE};
    EGLSurface surface = p_eglCreatePbufferSurface(display, config, surface_attributes);
    CHECK(surface != EGL_NO_SURFACE);
    CHECK(p_eglMakeCurrent(display, surface, surface, context));
    p_glClearColor(1, 0, 0, 1); p_glClear(GL_COLOR_BUFFER_BIT);
    unsigned char pixel[4] = {0};
    p_glReadPixels(1, 1, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, pixel);
    CHECK(p_glGetError() == GL_NO_ERROR);
    CHECK(pixel[0] == 255 && pixel[1] == 0 && pixel[2] == 0 && pixel[3] == 255);
    const char *vertex_source = "attribute vec2 position; void main() { gl_Position = vec4(position, 0.0, 1.0); }";
    const char *fragment_source = "precision mediump float; void main() { gl_FragColor = vec4(0.0, 1.0, 0.0, 1.0); }";
    GLuint vertex = p_glCreateShader(GL_VERTEX_SHADER);
    GLuint fragment = p_glCreateShader(GL_FRAGMENT_SHADER);
    p_glShaderSource(vertex, 1, &vertex_source, NULL); p_glCompileShader(vertex);
    p_glShaderSource(fragment, 1, &fragment_source, NULL); p_glCompileShader(fragment);
    GLint compiled;
    p_glGetShaderiv(vertex, GL_COMPILE_STATUS, &compiled); CHECK(compiled);
    p_glGetShaderiv(fragment, GL_COMPILE_STATUS, &compiled); CHECK(compiled);
    GLuint program = p_glCreateProgram();
    p_glAttachShader(program, vertex); p_glAttachShader(program, fragment);
    p_glBindAttribLocation(program, 0, "position"); p_glLinkProgram(program);
    p_glGetProgramiv(program, GL_LINK_STATUS, &compiled); CHECK(compiled);
    p_glUseProgram(program);
    const GLfloat positions[] = {-1, -1, 3, -1, -1, 3};
    p_glViewport(0, 0, 4, 4);
    p_glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, positions);
    p_glEnableVertexAttribArray(0); p_glDrawArrays(GL_TRIANGLES, 0, 3);
    p_glReadPixels(1, 1, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, pixel);
    CHECK(p_glGetError() == GL_NO_ERROR);
    CHECK(pixel[0] == 0 && pixel[1] == 255 && pixel[2] == 0 && pixel[3] == 255);
    printf("PASS HMOS EGL %d.%d GLES pbuffer pixel=%u,%u,%u,%u renderer=%s\n",
           major, minor, pixel[0], pixel[1], pixel[2], pixel[3], p_glGetString(GL_RENDERER));
    p_glDeleteProgram(program); p_glDeleteShader(vertex); p_glDeleteShader(fragment);
    CHECK(p_eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT));
    CHECK(p_eglDestroySurface(display, surface)); CHECK(p_eglDestroyContext(display, context));
    CHECK(p_eglTerminate(display));
    return 0;
}
