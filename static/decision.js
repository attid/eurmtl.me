document.addEventListener('DOMContentLoaded', function() {
    document.body.addEventListener('click', function(event) {
        if (event.target) {
            if (event.target.classList.contains('loadsDecisionNum')) {
                fetch(`/decision/number`)
                    .then(response => {
                        if (!response.ok) {
                            throw new Error("Network response was not ok");
                        }
                        return response.json();
                    })
                    .then(data => {
                        document.querySelector("#question_number").value = data.number;
                        // Получение текущего значения textarea
                        var currentText = document.querySelector("#inquiry").value;
                        // Обновление значения textarea
                        document.querySelector("#inquiry").value = "Вопрос " + data.number + ": " + currentText;
                    })
                    .catch(error => {
                        console.log("There was a problem with the fetch operation:", error.message);
                    });
            }

        }



    });

});
